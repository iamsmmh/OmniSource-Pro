"""Application repository for OmniSource."""

from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from omnisource.core.models.application import Application, OpenSourceStatus
from omnisource.core.models.category import Category
from omnisource.core.models.developer import Developer
from omnisource.core.models.license import License
from omnisource.core.models.platform import Architecture, Platform
from omnisource.core.models.release import Release, ReleaseAsset
from omnisource.core.models.scores import PopularityScore, QualityScore, TrustScore
from omnisource.core.repositories.base import BaseRepository, paginate_query
from omnisource.core.repositories.mappers import to_omnistore_app
from omnisource.core.schemas.omnistore import OmniStoreApp, PaginatedApps

# Relationship load options used to fully hydrate applications for API output.
_APP_LOAD_OPTIONS = (
    selectinload(Application.repositories),
    selectinload(Application.developer),
    selectinload(Application.organization),
    selectinload(Application.license),
    selectinload(Application.platforms),
    selectinload(Application.categories),
    selectinload(Application.tags),
    selectinload(Application.screenshots),
    selectinload(Application.icons),
    selectinload(Application.trust_score),
    selectinload(Application.quality_score),
    selectinload(Application.popularity_score),
    selectinload(Application.releases)
    .selectinload(Release.assets)
    .selectinload(ReleaseAsset.asset),
)


def _to_bool(value: Any) -> bool | None:
    """Coerce a loosely typed query value to a boolean or None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


class ApplicationRepository(BaseRepository[Application]):
    """Repository for application entities."""

    model = Application

    async def get_apps_paginated(
        self,
        page: int = 1,
        per_page: int = 30,
        q: str | None = None,
        platform: str | None = None,
        category: str | None = None,
        developer: str | None = None,
        license: str | None = None,
        architecture: str | None = None,
        open_source: Any | None = None,
        min_trust: Any | None = None,
        min_quality: Any | None = None,
        updated_since: str | None = None,
        sort: str | None = None,
        **kwargs: Any,
    ) -> PaginatedApps:
        """List applications with filtering, sorting, and pagination."""
        query = self._build_filtered_query(
            q=q,
            platform=platform,
            category=category,
            developer=developer,
            license=license,
            architecture=architecture,
            open_source=open_source,
            min_trust=min_trust,
            min_quality=min_quality,
            updated_since=updated_since,
        )

        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))

        query = self._apply_sort(query, sort)
        query = paginate_query(query, page=page, per_page=per_page)
        query = query.options(*_APP_LOAD_OPTIONS)

        result = await self.session.execute(query)
        apps = result.scalars().unique().all()

        return PaginatedApps(
            items=[to_omnistore_app(app) for app in apps],
            total=int(total or 0),
            page=page,
            freshness=datetime.utcnow().isoformat() + "Z",
        )

    async def get_app_by_id_or_slug(self, identifier: str) -> OmniStoreApp | None:
        """Get an application by app_id or slug."""
        query = (
            select(Application)
            .where(
                or_(
                    Application.app_id == identifier,
                    Application.slug == identifier,
                )
            )
            .options(*_APP_LOAD_OPTIONS)
        )
        result = await self.session.execute(query)
        app = result.scalars().first()
        return to_omnistore_app(app) if app else None

    async def get_apps_by_platform(self, platform: str) -> list[OmniStoreApp]:
        """Get all applications for a platform."""
        query = (
            select(Application)
            .join(Application.platforms)
            .where(Platform.platform_type == platform)
            .options(*_APP_LOAD_OPTIONS)
        )
        result = await self.session.execute(query)
        return [to_omnistore_app(app) for app in result.scalars().unique().all()]

    async def get_all_apps(self, limit: int | None = None) -> list[OmniStoreApp]:
        """Get all applications (optionally limited)."""
        query = select(Application).options(*_APP_LOAD_OPTIONS)
        if limit is not None:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return [to_omnistore_app(app) for app in result.scalars().unique().all()]

    async def get_trending(self, limit: int = 30) -> list[OmniStoreApp]:
        """Get trending applications ordered by popularity score."""
        query = (
            select(Application)
            .outerjoin(PopularityScore, PopularityScore.application_id == Application.id)
            .where(Application.is_active.is_(True))
            .order_by(func.coalesce(PopularityScore.normalized_score, 0).desc())
            .limit(limit)
            .options(*_APP_LOAD_OPTIONS)
        )
        result = await self.session.execute(query)
        return [to_omnistore_app(app) for app in result.scalars().unique().all()]

    async def get_latest(self, limit: int = 30) -> list[OmniStoreApp]:
        """Get latest applications ordered by creation time."""
        query = (
            select(Application)
            .where(Application.is_active.is_(True))
            .order_by(Application.created_at.desc())
            .limit(limit)
            .options(*_APP_LOAD_OPTIONS)
        )
        result = await self.session.execute(query)
        return [to_omnistore_app(app) for app in result.scalars().unique().all()]

    async def get_orm_by_app_id(self, app_id: str) -> Application | None:
        """Get the ORM application object by app_id."""
        result = await self.session.execute(select(Application).where(Application.app_id == app_id))
        return result.scalar_one_or_none()

    async def get_orm_by_slug(self, slug: str) -> Application | None:
        """Get the ORM application object by slug."""
        result = await self.session.execute(select(Application).where(Application.slug == slug))
        return result.scalar_one_or_none()

    def _build_filtered_query(
        self,
        q: str | None,
        platform: str | None,
        category: str | None,
        developer: str | None,
        license: str | None,
        architecture: str | None,
        open_source: Any | None,
        min_trust: Any | None,
        min_quality: Any | None,
        updated_since: str | None,
    ) -> Select:
        query = select(Application).where(Application.is_deleted.is_(False))

        if q:
            pattern = f"%{q.strip()}%"
            query = query.where(
                or_(
                    Application.name.ilike(pattern),
                    Application.short_description.ilike(pattern),
                    Application.app_id.ilike(pattern),
                    Application.slug.ilike(pattern),
                )
            )

        if platform:
            query = query.where(Application.platforms.any(Platform.platform_type == platform))
        if category:
            query = query.where(
                or_(
                    Application.categories.any(Category.slug == category),
                    Application.categories.any(Category.category_type == category),
                )
            )
        if developer:
            query = query.where(
                Application.developer.has(
                    or_(Developer.slug == developer, Developer.developer_id == developer)
                )
            )
        if license:
            query = query.where(Application.license.has(License.spdx_id == license))
        if architecture:
            query = query.where(
                Application.architectures.any(Architecture.architecture_type == architecture)
            )

        open_source_bool = _to_bool(open_source)
        if open_source_bool is True:
            query = query.where(
                Application.open_source_status.in_(
                    [OpenSourceStatus.OPEN_SOURCE, OpenSourceStatus.SOURCE_AVAILABLE]
                )
            )
        elif open_source_bool is False:
            query = query.where(Application.open_source_status == OpenSourceStatus.NOT_OPEN_SOURCE)

        if min_trust is not None:
            try:
                trust_val = float(min_trust)
                query = query.where(
                    Application.trust_score.has(TrustScore.normalized_score >= trust_val)
                )
            except (TypeError, ValueError):
                pass

        if min_quality is not None:
            try:
                quality_val = float(min_quality)
                query = query.where(
                    Application.quality_score.has(QualityScore.normalized_score >= quality_val)
                )
            except (TypeError, ValueError):
                pass

        updated = _parse_date(updated_since)
        if updated is not None:
            query = query.where(Application.updated_at >= updated)

        return query

    def _apply_sort(self, query: Select, sort: str | None) -> Select:
        sort = (sort or "name").lower()

        if sort in ("popularity", "relevance"):
            query = query.outerjoin(
                PopularityScore, PopularityScore.application_id == Application.id
            ).order_by(func.coalesce(PopularityScore.normalized_score, 0).desc())
        elif sort == "trust":
            query = query.outerjoin(
                TrustScore, TrustScore.application_id == Application.id
            ).order_by(func.coalesce(TrustScore.normalized_score, 0).desc())
        elif sort == "quality":
            query = query.outerjoin(
                QualityScore, QualityScore.application_id == Application.id
            ).order_by(func.coalesce(QualityScore.normalized_score, 0).desc())
        elif sort == "updated":
            query = query.order_by(Application.updated_at.desc())
        elif sort == "newest":
            query = query.order_by(Application.created_at.desc())
        else:  # name / default
            query = query.order_by(Application.name.asc())

        return query
