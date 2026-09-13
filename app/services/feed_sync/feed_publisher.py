"""Feed publisher: validated feed items -> PostgreSQL, atomically.

Publishing runs in a **single database transaction** per batch:

* any failure rolls the entire batch back (automatic rollback) - partial
  state is impossible by construction;
* on success the transaction commits, *then* best-effort side effects run
  (webhook emission, Meilisearch indexing, cache invalidation). Side-effect
  failures are logged and recorded in metrics but never undo the committed
  data.

Version conflicts (same version, different content) are reported, not
overwritten, so a malicious or buggy re-publish can never replace a verified
build silently.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.feed_sync.feed_deduplicator import FeedDeduplicator
from app.services.feed_sync.schemas import FeedItem
from omnisource.config.logging import get_logger
from omnisource.core.models.application import Application, ApplicationStatus
from omnisource.core.models.asset import Asset, AssetSource, AssetStatus
from omnisource.core.models.category import Category, Tag
from omnisource.core.models.developer import Developer
from omnisource.core.models.license import License
from omnisource.core.models.platform import Platform
from omnisource.core.models.release import ReleaseStatus
from omnisource.core.models.repository import Repository
from omnisource.core.models.source import Source, SourceType
from omnisource.core.repositories.release import ReleaseRepository
from omnisource.core.repositories.repository import RepositoryRepository
from omnisource.core.repositories.source import SourceRepository

logger = get_logger(__name__)

_SOURCE_TYPES = {
    "github": SourceType.GITHUB,
    "gitlab": SourceType.GITLAB,
    "codeberg": SourceType.CODEBERG,
    "gitea": SourceType.OTHER,
    "forgejo": SourceType.FORGEJO,
    "fmhy": SourceType.FMHY,
    "homebrew": SourceType.HOMEBREW,
    "fdroid": SourceType.FDROID,
    "flathub": SourceType.FLATHUB,
    "winget": SourceType.WINGET,
}


class FeedPublishError(Exception):
    """Raised when a publish batch fails after automatic rollback."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


@dataclass
class PublishResult:
    """Outcome of one publish batch."""

    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    releases_created: int = 0
    releases_updated: int = 0
    assets_created: int = 0

    @property
    def published(self) -> list[str]:
        return self.created + self.updated

    def to_dict(self) -> dict[str, Any]:
        return {
            "created": list(self.created),
            "updated": list(self.updated),
            "skipped": list(self.skipped),
            "conflicts": list(self.conflicts),
            "releases_created": self.releases_created,
            "releases_updated": self.releases_updated,
            "assets_created": self.assets_created,
        }


def _asset_id_for(url: str) -> str:
    """Deterministic asset identity so re-syncs are idempotent."""
    return "fs-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


class FeedPublisher:
    """Persists validated, normalized feed items with automatic rollback."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._deduplicator = FeedDeduplicator()
        self._repo_repo = RepositoryRepository(session)
        self._release_repo = ReleaseRepository(session)
        self._source_repo = SourceRepository(session)

    async def publish(self, items: list[FeedItem]) -> PublishResult:
        """Publish a batch atomically. Rolls back everything on failure."""
        if not items:
            return PublishResult()
        result = PublishResult()
        created_events: list[dict[str, Any]] = []
        updated_events: list[dict[str, Any]] = []
        try:
            for item in items:
                app, status = await self._publish_one(item, result)
                if app is None:
                    continue
                entry = self._app_payload(app)
                if status == "created":
                    result.created.append(item.app_id)
                    created_events.append(entry)
                elif status == "updated":
                    result.updated.append(item.app_id)
                    updated_events.append(entry)
            await self.session.commit()
        except Exception as exc:
            # Automatic rollback: the batch is all-or-nothing.
            try:
                await self.session.rollback()
            except Exception:  # pragma: no cover - defensive
                logger.error("Rollback failed after publish error", exc_info=True)
            logger.error("Feed publish batch failed; rolled back %d items: %s", len(items), exc)
            raise FeedPublishError(f"Feed publish failed, batch rolled back: {exc}") from exc

        await self._post_commit(created_events, updated_events, result)
        return result

    # ------------------------------------------------------------------
    # Per-item upsert (inside the batch transaction)
    # ------------------------------------------------------------------

    async def _publish_one(
        self, item: FeedItem, result: PublishResult
    ) -> tuple[Application | None, str | None]:
        source = await self._ensure_source(item.source)
        if source is None:
            result.skipped.append(item.app_id)
            return None, None

        repository = await self._upsert_repository(source, item)
        existing = await self._deduplicator.find_existing(self.session, item)

        conflicts = await self._deduplicator.detect_version_conflicts(self.session, existing, item)
        if conflicts:
            for conflict in conflicts:
                result.conflicts.append(f"{item.app_id}: {conflict}")
            logger.warning("Version conflicts for %s: %s", item.app_id, conflicts)

        developer = await self._upsert_developer(item)
        category = await self._primary_category(item)
        license_obj = await self._license(item.license)

        if existing is None:
            app = Application(
                app_id=item.app_id,
                slug=item.slug,
                name=item.name,
                bundle_id=item.bundle_id,
                category_id=category.id if category else None,
                short_description=(item.description or "")[:500] or None,
                long_description=item.description,
                homepage=item.homepage,
                documentation_url=item.documentation_url,
                status=ApplicationStatus.PUBLISHED,
                is_active=True,
                developer_id=developer.id if developer else None,
                license_id=license_obj.id if license_obj else None,
            )
            self.session.add(app)
            await self.session.flush()
            created = True
        else:
            app = existing
            self._apply_fields(app, item, developer, category, license_obj)
            created = False

        if repository not in app.repositories:
            app.repositories.append(repository)
        await self._sync_tags(app, item.tags)
        await self._sync_platforms(app, item.platforms)

        new_releases, updated_releases, new_assets = await self._upsert_releases(
            app, repository, item, conflicts
        )
        result.releases_created += new_releases
        result.releases_updated += updated_releases
        result.assets_created += new_assets

        return app, ("created" if created else "updated")

    def _apply_fields(
        self,
        app: Application,
        item: FeedItem,
        developer: Developer | None,
        category: Category | None,
        license_obj: License | None,
    ) -> None:
        changed = False
        for target, value in (
            ("name", item.name),
            ("short_description", (item.description or "")[:500] or None),
            ("long_description", item.description),
            ("homepage", item.homepage),
            ("documentation_url", item.documentation_url),
            ("bundle_id", item.bundle_id),
        ):
            if getattr(app, target) != value:
                setattr(app, target, value)
                changed = True
        if developer is not None and app.developer_id != developer.id:
            app.developer_id = developer.id
            changed = True
        if category is not None and app.category_id != category.id:
            app.category_id = category.id
            changed = True
        if license_obj is not None and app.license_id != license_obj.id:
            app.license_id = license_obj.id
            changed = True
        # Force a freshness stamp so updated_at-driven views move.
        from datetime import UTC, datetime

        app.updated_at = datetime.now(UTC)
        if not changed:
            logger.debug("Application %s unchanged; only freshness stamped", app.app_id)

    async def _ensure_source(self, source_name: str) -> Source | None:
        source_type = _SOURCE_TYPES.get(source_name.lower())
        if source_type is None:
            logger.warning("Unknown source type %r; skipping items", source_name)
            return None
        source = await self._source_repo.get_by_type(source_type)
        if source is None:
            source = await self._source_repo.ensure_default(
                name=source_name.title(),
                source_type=source_type,
                base_url=f"https://{source_name}.com",
                is_active=True,
            )
            await self.session.flush()
        return source

    async def _upsert_repository(self, source: Source, item: FeedItem) -> Repository:
        return await self._repo_repo.upsert_repository(
            source_id=source.id,
            external_id=item.repository,
            values={
                "full_name": item.repository,
                "name": item.repository.rsplit("/", 1)[-1],
                "description": item.description,
                "html_url": f"https://github.com/{item.repository}"
                if item.source.lower() == "github"
                else item.homepage,
                "stars": item.stars,
                "forks": item.forks,
                "pushed_at": item.pushed_at,
            },
        )

    async def _upsert_developer(self, item: FeedItem) -> Developer | None:
        owner = item.owner
        result = await self.session.execute(
            select(Developer).where(
                (Developer.developer_id == owner) | (Developer.slug == owner.lower())
            )
        )
        developer = result.scalars().first()
        if developer is None:
            developer = Developer(developer_id=owner, slug=owner.lower(), name=owner)
            self.session.add(developer)
            await self.session.flush()
        return developer

    async def _primary_category(self, item: FeedItem) -> Category | None:
        for tag in item.tags:
            result = await self.session.execute(select(Category).where(Category.slug == tag))
            category = result.scalars().first()
            if category is not None and category.is_active:
                return category
        return None

    async def _license(self, spdx: str | None) -> License | None:
        if not spdx:
            return None
        result = await self.session.execute(select(License).where(License.spdx_id == spdx))
        return result.scalars().first()

    async def _sync_tags(self, app: Application, tags: list[str]) -> None:
        if not tags:
            return
        for tag_name in tags:
            result = await self.session.execute(select(Tag).where(Tag.slug == tag_name))
            tag = result.scalars().first()
            if tag is None:
                tag = Tag(name=tag_name.title(), slug=tag_name)
                self.session.add(tag)
                await self.session.flush()
            if tag not in app.tags:
                app.tags.append(tag)

    async def _sync_platforms(self, app: Application, platforms: Sequence[str]) -> None:
        for platform_type in platforms:
            result = await self.session.execute(
                select(Platform).where(Platform.platform_type == platform_type)
            )
            platform = result.scalars().first()
            if platform is None:
                platform = Platform(
                    platform_type=platform_type,
                    name=platform_type,
                    display_name=platform_type.title(),
                    is_active=True,
                )
                self.session.add(platform)
                await self.session.flush()
            if platform not in app.platforms:
                app.platforms.append(platform)

    async def _upsert_releases(
        self,
        app: Application,
        repository: Repository,
        item: FeedItem,
        conflicts: list[str],
    ) -> tuple[int, int, int]:
        """Upsert releases and assets. Returns (releases_created, releases_updated, assets_created)."""
        new_releases = updated_releases = new_assets = 0
        conflict_versions = {conflict.split(" ", 1)[1].split(":", 1)[0] for conflict in conflicts}

        for feed_release in item.releases:
            external_id = f"{feed_release.tag or feed_release.version}"
            release, created = await self._release_repo.upsert_release(
                application_id=app.id,
                repository_id=repository.id,
                external_id=external_id,
                values={
                    "version": feed_release.version,
                    "tag": feed_release.tag,
                    "status": ReleaseStatus.PRERELEASE
                    if feed_release.is_prerelease
                    else ReleaseStatus.RELEASED,
                    "body": feed_release.notes,
                    "is_prerelease": feed_release.is_prerelease,
                    "published_at": feed_release.published_at,
                },
            )
            if created:
                new_releases += 1
            else:
                updated_releases += 1

            if feed_release.version in conflict_versions and not created:
                # Do not re-link assets that are part of a content conflict.
                logger.warning(
                    "Skipping asset uplink for conflicted release %s of %s",
                    feed_release.version,
                    item.app_id,
                )
                continue

            for feed_asset in feed_release.assets:
                asset, asset_created = await self._upsert_asset(feed_asset)
                await self._release_repo.link_asset(release.id, asset.id)
                if asset_created:
                    new_assets += 1
        return new_releases, updated_releases, new_assets

    async def _upsert_asset(self, feed_asset) -> tuple[Asset, bool]:
        asset_id = _asset_id_for(feed_asset.url)
        result = await self.session.execute(select(Asset).where(Asset.asset_id == asset_id))
        asset = result.scalars().first()
        values = {
            "filename": feed_asset.filename,
            "download_url": feed_asset.url,
            "browser_download_url": feed_asset.url,
            "size_bytes": feed_asset.size_bytes,
            "sha256": feed_asset.sha256,
            "detected_platform": feed_asset.platform,
            "detected_architecture": feed_asset.architecture,
            "package_type": feed_asset.package_type,
            "status": AssetStatus.PENDING,
            "source": AssetSource.GITHUB_RELEASE,
        }
        if asset is None:
            asset = Asset(asset_id=asset_id, **values)
            self.session.add(asset)
            await self.session.flush()
            return asset, True
        for key, value in values.items():
            setattr(asset, key, value)
        await self.session.flush()
        return asset, False

    # ------------------------------------------------------------------
    # Payloads + post-commit side effects
    # ------------------------------------------------------------------

    @staticmethod
    def _app_payload(app: Application) -> dict[str, Any]:
        return {
            "app_id": app.app_id,
            "id": str(app.id),
            "slug": app.slug,
            "name": app.name,
            "bundle_id": app.bundle_id,
            "description": app.short_description,
            "homepage": app.homepage,
            "license": app.license.spdx_id if app.license else None,
            "platforms": [p.platform_type for p in app.platforms],
            "tags": [t.slug for t in app.tags],
            "status": app.status.value,
            "updated_at": app.updated_at.isoformat() if app.updated_at else None,
        }

    async def _post_commit(
        self,
        created_events: list[dict[str, Any]],
        updated_events: list[dict[str, Any]],
        result: PublishResult,
    ) -> None:
        """Best-effort side effects after the transaction is durable."""
        await self._emit_webhooks(created_events, updated_events)
        await self._index_search(result.published)
        await self._invalidate_cache(result.published)

    async def _emit_webhooks(
        self,
        created_events: list[dict[str, Any]],
        updated_events: list[dict[str, Any]],
    ) -> None:
        if not (created_events or updated_events):
            return
        try:
            from omnisource.automation.notify import dispatch_event

            if created_events:
                await dispatch_event(
                    self.session,
                    "app_created",
                    {"applications": created_events, "count": len(created_events)},
                )
            if updated_events:
                await dispatch_event(
                    self.session,
                    "app_updated",
                    {"applications": updated_events, "count": len(updated_events)},
                )
        except Exception:
            logger.warning("Webhook emission after publish failed", exc_info=True)

    async def _index_search(self, app_ids: list[str]) -> None:
        if not app_ids:
            return
        try:
            from omnisource.core.repositories.application import ApplicationRepository
            from omnisource.search.indexer import get_indexer

            indexer = get_indexer()
            repo = ApplicationRepository(self.session)
            documents = []
            for app_id in app_ids:
                app = await repo.get_app_by_id_or_slug(app_id)
                if app is not None:
                    documents.append(app.model_dump(mode="json"))
            if documents:
                indexer.index_apps(documents)
        except Exception:
            logger.warning("Search indexing after publish failed", exc_info=True)

    async def _invalidate_cache(self, app_ids: list[str]) -> None:
        if not app_ids:
            return
        try:
            from omnisource.cache.invalidation import invalidate_feed_sync

            await invalidate_feed_sync(app_ids)
        except Exception:
            logger.warning("Cache invalidation after publish failed", exc_info=True)

    # ------------------------------------------------------------------
    # Deletions
    # ------------------------------------------------------------------

    async def deactivate(
        self, app_id: str, reason: str = "removed by source"
    ) -> Application | None:
        """Soft-delete an application (source removed it) and emit app_deleted."""
        result = await self.session.execute(
            select(Application).where((Application.app_id == app_id) | (Application.slug == app_id))
        )
        app = result.scalars().first()
        if app is None:
            return None
        try:
            logger.info("Deactivating application %s: %s", app.app_id, reason)
            app.is_active = False
            app.status = ApplicationStatus.REJECTED
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            raise FeedPublishError(f"deactivate failed for {app_id}: {exc}") from exc
        try:
            from omnisource.automation.notify import dispatch_event

            await dispatch_event(self.session, "app_deleted", {"app_id": app_id, "reason": reason})
            from omnisource.cache.invalidation import invalidate_app

            await invalidate_app(app_id)
        except Exception:
            logger.warning("Post-deactivate side effects failed for %s", app_id, exc_info=True)
        return app


__all__ = ["FeedPublishError", "FeedPublisher", "PublishResult"]
