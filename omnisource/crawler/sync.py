"""Repository synchronization service: releases, assets, applications."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from omnisource.config.logging import get_logger
from omnisource.connectors.base import SourceConnector
from omnisource.connectors.registry import create_connector
from omnisource.core.models.application import (
    Application,
    OpenSourceStatus,
    application_platforms,
)
from omnisource.core.models.asset import Asset, AssetSource, AssetStatus
from omnisource.core.models.category import Category, Tag
from omnisource.core.models.developer import Developer
from omnisource.core.models.license import License
from omnisource.core.models.platform import Architecture, Platform
from omnisource.core.models.release import Release, ReleaseStatus
from omnisource.core.models.repository import Repository
from omnisource.core.models.scores import PopularityScore, QualityScore, TrustScore
from omnisource.core.models.source import SourceType
from omnisource.core.repositories.release import ReleaseRepository
from omnisource.core.repositories.repository import RepositoryRepository
from omnisource.core.repositories.source import SourceRepository
from omnisource.core.schemas.repository import RepositorySchema
from omnisource.crawler.policies import ProcessingPolicies
from omnisource.intelligence.scoring import ScoringEngine
from omnisource.processing.categorization import categorize
from omnisource.processing.deduplication import slugify
from omnisource.processing.license_engine import normalize_license
from omnisource.processing.validation.asset_validator import validate_asset

logger = get_logger(__name__)


class RepositorySyncService:
    """Synchronizes repositories, releases, assets, and applications."""

    def __init__(self, session: AsyncSession, policies: ProcessingPolicies | None = None):
        self.session = session
        self.policies = policies or ProcessingPolicies.from_settings()
        self.scoring = ScoringEngine()

        # In-session caches avoid duplicate lookups/inserts within a batch.
        self._developer_cache: dict[str, Developer] = {}
        self._license_cache: dict[str, License] = {}
        self._category_cache: dict[str, Category] = {}
        self._tag_cache: dict[str, Tag] = {}
        self._platform_cache: dict[str, Platform] = {}
        self._architecture_cache: dict[str, Architecture] = {}

    async def sync_source(
        self, source_type: str = "github", limit: int | None = None
    ) -> dict[str, Any]:
        """Synchronize all repositories for a source type."""
        source_repo = SourceRepository(self.session)
        source = await source_repo.get_by_type(SourceType(source_type))
        if source is None:
            return {"source": source_type, "repositories": 0, "releases": 0, "assets": 0}

        repository_repo = RepositoryRepository(self.session)
        repositories = await repository_repo.list_repositories(
            source_id=source.id, limit=limit or 1000
        )

        connector = create_connector(source_type)
        await connector.initialize()

        total_releases = 0
        total_assets = 0
        try:
            for repository in repositories:
                result = await self.sync_repository(connector, repository)
                total_releases += result["releases"]
                total_assets += result["assets"]
            await self.session.commit()
        finally:
            await connector.close()

        return {
            "source": source_type,
            "repositories": len(repositories),
            "releases": total_releases,
            "assets": total_assets,
        }

    async def sync_repository(
        self,
        connector: SourceConnector,
        repository: Repository,
    ) -> dict[str, Any]:
        """Synchronize releases and assets for a single repository."""
        repo_schema = RepositorySchema.model_validate(repository)

        try:
            releases = await connector.get_releases(repo_schema)
        except Exception as exc:
            logger.warning("Failed to fetch releases for %s: %s", repository.full_name, exc)
            return {"releases": 0, "assets": 0}

        app = await self._ensure_application(repository)

        release_repo = ReleaseRepository(self.session)
        asset_count = 0
        for release_schema in releases[: self.policies.max_releases_per_repo]:
            status_value = getattr(release_schema.status, "value", release_schema.status)
            release = await release_repo.upsert_release(
                application_id=app.id,
                repository_id=repository.id,
                external_id=release_schema.external_id,
                values={
                    "version": release_schema.version,
                    "tag": release_schema.tag,
                    "name": release_schema.name,
                    "body": release_schema.body,
                    "status": ReleaseStatus(status_value),
                    "is_prerelease": release_schema.is_prerelease,
                    "is_draft": release_schema.is_draft,
                    "published_at": release_schema.published_at,
                    "created_at_external": release_schema.created_at_external,
                    "commit_sha": release_schema.commit_sha,
                    "tarball_url": release_schema.tarball_url,
                    "zipball_url": release_schema.zipball_url,
                    "download_count": release_schema.download_count,
                },
            )

            assets = await connector.get_assets(release_schema)
            for asset_schema in assets[: self.policies.max_assets_per_release]:
                asset = await self._upsert_asset(app, release, asset_schema.model_dump())
                await release_repo.link_asset(release.id, asset.id)
                asset_count += 1

        await self._compute_scores(app, repository)
        return {"releases": len(releases), "assets": asset_count}

    async def _ensure_application(self, repository: Repository) -> Application:
        """Get or create the application for a repository."""
        result = await self.session.execute(
            select(Application)
            .where(Application.app_id == repository.full_name)
            .options(
                selectinload(Application.repositories),
                selectinload(Application.categories),
                selectinload(Application.tags),
                selectinload(Application.platforms),
                selectinload(Application.architectures),
                selectinload(Application.developer),
                selectinload(Application.license),
            )
        )
        app = result.scalar_one_or_none()

        if app is None:
            app = Application(
                app_id=repository.full_name,
                slug=slugify(repository.name),
                name=repository.name,
                short_description=(repository.description or "")[:500] or None,
                long_description=repository.description,
                homepage=repository.homepage,
                open_source_status=OpenSourceStatus.OPEN_SOURCE,
                is_active=True,
            )
            self.session.add(app)
            # Initialize relationship collections now (while the instance is
            # transient) so later membership checks/appends do not trigger
            # async lazy loads on a persistent instance.
            app.repositories = []
            app.categories = []
            app.tags = []
            app.platforms = []
            app.architectures = []

        if repository not in (app.repositories or []):
            app.repositories.append(repository)

        # Developer from repository owner
        owner = repository.full_name.split("/")[0] if "/" in repository.full_name else "unknown"
        if app.developer is None:
            app.developer = await self._get_or_create_developer(owner)

        # License from repository metadata
        metadata = await repository.awaitable_attrs.metadata_obj
        license_spdx = normalize_license(metadata.license_spdx) if metadata else None
        if license_spdx and app.license is None:
            app.license = await self._get_or_create_license(license_spdx)

        # Categories and tags from topics
        topics = metadata.topics if metadata else []
        await self._classify(app, topics)

        await self.session.flush()
        return app

    async def _get_or_create_developer(self, owner: str) -> Developer:
        if owner in self._developer_cache:
            return self._developer_cache[owner]
        result = await self.session.execute(
            select(Developer).where(Developer.developer_id == owner)
        )
        developer = result.scalar_one_or_none()
        if developer is None:
            developer = Developer(developer_id=owner, slug=owner, name=owner)
            self.session.add(developer)
        self._developer_cache[owner] = developer
        return developer

    async def _get_or_create_license(self, spdx_id: str) -> License:
        if spdx_id in self._license_cache:
            return self._license_cache[spdx_id]
        result = await self.session.execute(select(License).where(License.spdx_id == spdx_id))
        license_obj = result.scalar_one_or_none()
        if license_obj is None:
            license_obj = License(
                license_id=spdx_id.lower(),
                spdx_id=spdx_id,
                name=spdx_id,
                short_name=spdx_id,
                is_osi_approved=True,
            )
            self.session.add(license_obj)
        self._license_cache[spdx_id] = license_obj
        return license_obj

    async def _classify(self, app: Application, topics: list[str]) -> None:
        category_types = categorize(topics=topics, description=app.short_description)
        for category_type in category_types:
            category = await self._get_or_create_category(category_type)
            if category not in (app.categories or []):
                app.categories.append(category)

        for topic in topics[:10]:
            tag = await self._get_or_create_tag(topic)
            if tag not in (app.tags or []):
                app.tags.append(tag)

    async def _get_or_create_category(self, category_type: str) -> Category:
        if category_type in self._category_cache:
            return self._category_cache[category_type]
        result = await self.session.execute(
            select(Category).where(Category.category_type == category_type)
        )
        category = result.scalar_one_or_none()
        if category is None:
            category = Category(
                category_type=category_type,
                name=category_type,
                slug=slugify(category_type),
            )
            self.session.add(category)
        self._category_cache[category_type] = category
        return category

    async def _get_or_create_tag(self, name: str) -> Tag:
        slug = slugify(name)
        if slug in self._tag_cache:
            return self._tag_cache[slug]
        result = await self.session.execute(select(Tag).where(Tag.slug == slug))
        tag = result.scalar_one_or_none()
        if tag is None:
            tag = Tag(name=name, slug=slug)
            self.session.add(tag)
        self._tag_cache[slug] = tag
        return tag

    async def _upsert_asset(
        self,
        app: Application,
        release: Release,
        data: dict[str, Any],
    ) -> Asset:
        outcome = validate_asset(data)
        status = AssetStatus(outcome.status)

        result = await self.session.execute(
            select(Asset).where(Asset.asset_id == data.get("asset_id"))
        )
        asset = result.scalar_one_or_none()

        values = {
            "filename": data.get("filename") or "",
            "display_name": data.get("display_name"),
            "download_url": data.get("download_url") or "",
            "browser_download_url": data.get("browser_download_url"),
            "size_bytes": data.get("size_bytes"),
            "mime_type": data.get("mime_type"),
            "file_type": data.get("file_type"),
            "detected_platform": data.get("detected_platform"),
            "detected_architecture": data.get("detected_architecture"),
            "platform_confidence": data.get("platform_confidence", 0.0),
            "architecture_confidence": data.get("architecture_confidence", 0.0),
            "package_type": data.get("package_type"),
            "version": data.get("version") or release.version,
            "sha256": data.get("sha256"),
            "sha512": data.get("sha512"),
            "status": status,
            "source": AssetSource(data.get("source") or "other"),
            "validation_status": outcome.status,
            "validation_message": "; ".join(outcome.errors + outcome.warnings)[:500] or None,
            "download_count": data.get("download_count", 0),
        }

        if asset is None:
            asset = Asset(
                asset_id=data.get("asset_id") or f"{release.external_id}-{data.get('filename')}",
                **values,
            )
            self.session.add(asset)
        else:
            for key, value in values.items():
                setattr(asset, key, value)

        if data.get("detected_platform"):
            platform = await self._get_or_create_platform(data["detected_platform"])
            asset.platform_id = platform.id
            if platform not in (app.platforms or []):
                app.platforms.append(platform)
        if data.get("detected_architecture"):
            architecture = await self._get_or_create_architecture(data["detected_architecture"])
            asset.architecture_id = architecture.id
            if architecture not in (app.architectures or []):
                app.architectures.append(architecture)

        await self.session.flush()
        return asset

    async def _get_or_create_platform(self, platform_type: str) -> Platform:
        if platform_type in self._platform_cache:
            return self._platform_cache[platform_type]
        result = await self.session.execute(
            select(Platform).where(Platform.platform_type == platform_type)
        )
        platform = result.scalar_one_or_none()
        if platform is None:
            platform = Platform(
                platform_type=platform_type,
                name=platform_type,
                display_name=platform_type.title(),
                is_active=True,
            )
            self.session.add(platform)
            await self.session.flush()
        self._platform_cache[platform_type] = platform
        return platform

    async def _get_or_create_architecture(self, architecture_type: str) -> Architecture:
        if architecture_type in self._architecture_cache:
            return self._architecture_cache[architecture_type]
        result = await self.session.execute(
            select(Architecture).where(Architecture.architecture_type == architecture_type)
        )
        architecture = result.scalar_one_or_none()
        if architecture is None:
            architecture = Architecture(
                architecture_type=architecture_type,
                name=architecture_type,
                display_name=architecture_type,
                aliases=[],
            )
            self.session.add(architecture)
            await self.session.flush()
        self._architecture_cache[architecture_type] = architecture
        return architecture

    async def _compute_scores(self, app: Application, repository: Repository) -> None:
        metadata = await repository.awaitable_attrs.metadata_obj

        release_objs = (
            (await self.session.execute(select(Release).where(Release.application_id == app.id)))
            .scalars()
            .all()
        )

        platform_count = int(
            await self.session.scalar(
                select(func.count())
                .select_from(application_platforms)
                .where(application_platforms.c.application_id == app.id)
            )
            or 0
        )

        metrics = self.scoring.build_metrics(
            open_source=app.open_source_status == OpenSourceStatus.OPEN_SOURCE,
            has_license=app.license_id is not None,
            has_readme=bool(metadata and metadata.readme),
            has_description=bool(app.long_description),
            stars=repository.stars,
            forks=repository.forks,
            contributors=metadata.contributors_count if metadata else 0,
            has_releases=bool(release_objs),
            release_count=len(release_objs),
            platform_count=platform_count,
            valid_asset_ratio=0.8,
        )
        scores = self.scoring.compute_all(metrics)

        trust = await self._get_or_create_score(TrustScore, app.id)
        trust.score = scores["trust"]["score"]
        trust.normalized_score = scores["trust"]["normalized_score"]
        trust.factors = scores["trust"]["factors"]

        quality = await self._get_or_create_score(QualityScore, app.id)
        quality.score = scores["quality"]["score"]
        quality.normalized_score = scores["quality"]["normalized_score"]
        quality.factors = scores["quality"]["factors"]

        popularity = await self._get_or_create_score(PopularityScore, app.id)
        popularity.score = scores["popularity"]["score"]
        popularity.normalized_score = scores["popularity"]["normalized_score"]
        popularity.factors = scores["popularity"]["factors"]
        popularity.github_stars = scores["popularity"]["github_stars"]
        popularity.github_forks = scores["popularity"]["github_forks"]
        popularity.release_downloads = scores["popularity"]["release_downloads"]
        popularity.contributors = scores["popularity"]["contributors"]

        await self.session.flush()

    async def _get_or_create_score(self, model, application_id: UUID):
        result = await self.session.execute(
            select(model).where(model.application_id == application_id)
        )
        score = result.scalar_one_or_none()
        if score is None:
            score = model(application_id=application_id)
            self.session.add(score)
            await self.session.flush()
        return score
