"""Scalable, explainable application recommendation service.

The service persists content-based edges in ``application_relationships`` and
uses aggregate pseudonymous interactions only as a secondary collaborative
signal.  It deliberately starts from indexed shared category/tag/platform
candidates rather than comparing every pair of applications, avoiding an
O(n²) full-catalog scan at production catalogue sizes.
"""

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.core.models.application import (
    Application,
    ApplicationRelationship,
    ApplicationRelationshipType,
)
from omnisource.core.models.category import Category, Tag
from omnisource.core.models.experience import AnalyticsEvent, InteractionType
from omnisource.core.models.platform import Platform
from omnisource.core.models.scores import PopularityScore
from omnisource.core.repositories.application import _APP_LOAD_OPTIONS
from omnisource.core.repositories.mappers import to_omnistore_app
from omnisource.core.schemas.recommendations import (
    RecommendationItem,
    RecommendationKind,
    RecommendationResponse,
)

ALGORITHM_VERSION = "v1"


def _tokens(items: Iterable[object]) -> set[str]:
    return {
        str(getattr(item, "slug", None) or getattr(item, "platform_type", None) or "").lower()
        for item in items
    } - {""}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


class RecommendationService:
    """Builds and serves content, collaborative, and catalogue recommendations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _application(self, identifier: str) -> Application | None:
        result = await self.session.execute(
            select(Application)
            .where(or_(Application.app_id == identifier, Application.slug == identifier))
            .options(*_APP_LOAD_OPTIONS)
        )
        return result.scalars().first()

    async def _applications_by_ids(self, identifiers: list[UUID]) -> dict[UUID, Application]:
        if not identifiers:
            return {}
        result = await self.session.execute(
            select(Application).where(Application.id.in_(identifiers)).options(*_APP_LOAD_OPTIONS)
        )
        return {app.id: app for app in result.scalars().unique().all()}

    @staticmethod
    def _similarity(source: Application, candidate: Application) -> tuple[float, list[str]]:
        source_tags = _tokens(source.tags)
        candidate_tags = _tokens(candidate.tags)
        source_categories = _tokens(source.categories)
        candidate_categories = _tokens(candidate.categories)
        source_platforms = _tokens(source.platforms)
        candidate_platforms = _tokens(candidate.platforms)

        tag_similarity = _jaccard(source_tags, candidate_tags)
        category_similarity = _jaccard(source_categories, candidate_categories)
        platform_similarity = _jaccard(source_platforms, candidate_platforms)
        developer_match = bool(
            source.developer_id and source.developer_id == candidate.developer_id
        )
        score = min(
            1.0,
            0.55 * tag_similarity
            + 0.30 * category_similarity
            + 0.10 * platform_similarity
            + (0.05 if developer_match else 0.0),
        )
        reasons: list[str] = []
        if source_tags & candidate_tags:
            reasons.append("shared_tags")
        if source_categories & candidate_categories:
            reasons.append("shared_categories")
        if source_platforms & candidate_platforms:
            reasons.append("shared_platforms")
        if developer_match:
            reasons.append("same_developer")
        return round(score, 4), reasons

    async def rebuild_for_app(self, identifier: str, candidate_limit: int = 200) -> int:
        """Build or refresh graph edges for one app from indexed shared candidates.

        This bounded operation is appropriate for a background task after a
        sync.  It never scans the entire catalogue in Python.
        """
        app = await self._application(identifier)
        if app is None:
            return 0

        category_ids = [category.id for category in app.categories]
        tag_ids = [tag.id for tag in app.tags]
        platform_ids = [platform.id for platform in app.platforms]
        conditions = []
        if category_ids:
            conditions.append(Application.categories.any(Category.id.in_(category_ids)))
        if tag_ids:
            conditions.append(Application.tags.any(Tag.id.in_(tag_ids)))
        if platform_ids:
            conditions.append(Application.platforms.any(Platform.id.in_(platform_ids)))
        if app.developer_id:
            conditions.append(Application.developer_id == app.developer_id)
        if not conditions:
            return 0

        result = await self.session.execute(
            select(Application)
            .where(
                Application.id != app.id,
                Application.is_active.is_(True),
                Application.is_deleted.is_(False),
                or_(*conditions),
            )
            .limit(candidate_limit)
            .options(*_APP_LOAD_OPTIONS)
        )
        candidates = result.scalars().unique().all()

        existing_rows = await self.session.execute(
            select(ApplicationRelationship).where(
                ApplicationRelationship.from_app_id == app.id,
                ApplicationRelationship.to_app_id.in_([candidate.id for candidate in candidates]),
            )
        )
        existing = {
            (edge.to_app_id, edge.relationship_type): edge for edge in existing_rows.scalars().all()
        }
        persisted = 0
        for candidate in candidates:
            score, _ = self._similarity(app, candidate)
            if score < 0.25:
                continue
            relation_type = (
                ApplicationRelationshipType.ALTERNATIVE_TO
                if score >= 0.65
                else ApplicationRelationshipType.SIMILAR_TO
            )
            edge = existing.get((candidate.id, relation_type))
            if edge is None:
                edge = ApplicationRelationship(
                    from_app_id=app.id,
                    to_app_id=candidate.id,
                    relationship_type=relation_type,
                    confidence=score,
                    method="content_v1",
                )
                self.session.add(edge)
            else:
                edge.confidence = score
                edge.method = "content_v1"
            persisted += 1
        await self.session.flush()
        return persisted

    async def _graph_items(
        self,
        app: Application,
        kinds: set[ApplicationRelationshipType],
        limit: int,
    ) -> list[RecommendationItem]:
        rows = await self.session.execute(
            select(ApplicationRelationship)
            .where(
                ApplicationRelationship.from_app_id == app.id,
                ApplicationRelationship.relationship_type.in_(kinds),
            )
            .order_by(ApplicationRelationship.confidence.desc())
            .limit(limit)
        )
        edges = rows.scalars().all()
        applications = await self._applications_by_ids([edge.to_app_id for edge in edges])
        items: list[RecommendationItem] = []
        for edge in edges:
            candidate = applications.get(edge.to_app_id)
            if candidate is None or not candidate.is_active or candidate.is_deleted:
                continue
            kind = (
                RecommendationKind.ALTERNATIVE
                if edge.relationship_type == ApplicationRelationshipType.ALTERNATIVE_TO
                else RecommendationKind.SIMILAR
            )
            items.append(
                RecommendationItem(
                    app=to_omnistore_app(candidate),
                    score=max(0.0, min(1.0, edge.confidence)),
                    kind=kind,
                    reasons=[edge.method or "catalogue_relationship"],
                )
            )
        return items

    async def related(
        self, identifier: str, relationship: str = "all", limit: int = 20
    ) -> RecommendationResponse:
        """Return persisted graph recommendations, rebuilding once if needed."""
        app = await self._application(identifier)
        if app is None:
            return RecommendationResponse(
                subject_app_id=identifier,
                generated_at=datetime.now(UTC),
                items=[],
            )
        kinds = {
            ApplicationRelationshipType.SIMILAR_TO,
            ApplicationRelationshipType.ALTERNATIVE_TO,
        }
        if relationship == "similar":
            kinds = {ApplicationRelationshipType.SIMILAR_TO}
        elif relationship == "alternative":
            kinds = {ApplicationRelationshipType.ALTERNATIVE_TO}
        items = await self._graph_items(app, kinds, limit)
        if not items:
            await self.rebuild_for_app(identifier)
            items = await self._graph_items(app, kinds, limit)
        return RecommendationResponse(
            subject_app_id=app.app_id,
            algorithm_version=ALGORITHM_VERSION,
            generated_at=datetime.now(UTC),
            items=items,
        )

    async def collaborative(self, identifier: str, limit: int = 20) -> list[RecommendationItem]:
        """Return privacy-safe co-engagement recommendations for an application."""
        app = await self._application(identifier)
        if app is None:
            return []
        engaged_subjects = (
            select(AnalyticsEvent.subject_hash)
            .where(
                AnalyticsEvent.application_id == app.id,
                AnalyticsEvent.subject_hash.is_not(None),
                AnalyticsEvent.event_type.in_([InteractionType.FAVORITE, InteractionType.INSTALL]),
            )
            .distinct()
            .subquery()
        )
        rows = await self.session.execute(
            select(
                AnalyticsEvent.application_id, func.count(AnalyticsEvent.id).label("engagements")
            )
            .where(
                AnalyticsEvent.subject_hash.in_(select(engaged_subjects.c.subject_hash)),
                AnalyticsEvent.application_id.is_not(None),
                AnalyticsEvent.application_id != app.id,
                AnalyticsEvent.event_type.in_([InteractionType.FAVORITE, InteractionType.INSTALL]),
            )
            .group_by(AnalyticsEvent.application_id)
            .order_by(func.count(AnalyticsEvent.id).desc())
            .limit(limit)
        )
        ranked = [(app_id, int(count)) for app_id, count in rows.all() if app_id is not None]
        applications = await self._applications_by_ids([item[0] for item in ranked])
        top_count = max((count for _, count in ranked), default=1)
        return [
            RecommendationItem(
                app=to_omnistore_app(candidate),
                score=round(count / top_count, 4),
                kind=RecommendationKind.COLLABORATIVE,
                reasons=["co_engagement"],
            )
            for candidate_id, count in ranked
            if (candidate := applications.get(candidate_id)) is not None
        ]

    async def catalogue(
        self, kind: RecommendationKind, limit: int, category: str | None = None
    ) -> RecommendationResponse:
        """Return trending, popular, new, or category catalogue recommendations."""
        query: Select = select(Application).where(
            Application.is_active.is_(True), Application.is_deleted.is_(False)
        )
        if category:
            query = query.where(Application.categories.any(Category.slug == category))
        if kind in {RecommendationKind.TRENDING, RecommendationKind.POPULAR}:
            query = query.outerjoin(
                PopularityScore, PopularityScore.application_id == Application.id
            ).order_by(func.coalesce(PopularityScore.normalized_score, 0).desc())
        else:
            query = query.order_by(Application.created_at.desc())
        result = await self.session.execute(query.limit(limit).options(*_APP_LOAD_OPTIONS))
        apps = result.scalars().unique().all()
        max_popularity = max(
            (float(app.popularity_score.normalized_score) for app in apps if app.popularity_score),
            default=100.0,
        )
        return RecommendationResponse(
            algorithm_version=ALGORITHM_VERSION,
            generated_at=datetime.now(UTC),
            items=[
                RecommendationItem(
                    app=to_omnistore_app(app),
                    score=round(
                        min(
                            1.0,
                            float(app.popularity_score.normalized_score) / max(max_popularity, 1.0),
                        )
                        if app.popularity_score
                        and kind in {RecommendationKind.TRENDING, RecommendationKind.POPULAR}
                        else 1.0,
                        4,
                    ),
                    kind=kind,
                    reasons=[f"catalogue_{kind.value}" if not category else "category_match"],
                )
                for app in apps
            ],
        )


__all__ = ["ALGORITHM_VERSION", "RecommendationService"]
