"""Content-based related-app recommendations.

Scoring combines four signals (documented, deterministic, explainable):

    shared category       up to 40 pts  (exact primary-category match,
                                        25 for any category overlap)
    shared tags           up to 30 pts  (Jaccard similarity of tag sets)
    developer similarity  up to 20 pts  (same developer/organization)
    popularity            up to 10 pts  (normalized popularity score,
                                        log-scaled to avoid dominance)

Each candidate above the threshold is returned with its per-signal
breakdown so clients can render "Why this app?".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from omnisource.core.models.application import Application
from omnisource.core.models.category import Category, Tag
from omnisource.core.models.scores import PopularityScore

MAX_CANDIDATES = 200
MIN_SCORE = 5.0

WEIGHT_CATEGORY = 40.0
WEIGHT_TAGS = 30.0
WEIGHT_DEVELOPER = 20.0
WEIGHT_POPULARITY = 10.0


@dataclass
class RelatedApp:
    """A scored recommendation with an explainable breakdown."""

    app: Application
    score: float
    reasons: dict[str, float] = field(default_factory=dict)
    shared_tags: list[str] = field(default_factory=list)
    shared_categories: list[str] = field(default_factory=list)


@dataclass
class RelatedAppsResult:
    subject_app_id: str
    items: list[RelatedApp] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.subject_app_id,
            "items": [
                {
                    "app_id": item.app.app_id,
                    "slug": item.app.slug,
                    "name": item.app.name,
                    "score": round(item.score, 2),
                    "reasons": {k: round(v, 2) for k, v in item.reasons.items()},
                    "shared_tags": item.shared_tags,
                    "shared_categories": item.shared_categories,
                    "description": item.app.short_description,
                    "homepage": item.app.homepage,
                    "bundle_id": item.app.bundle_id,
                    "license": item.app.license.spdx_id if item.app.license else None,
                    "platforms": [p.platform_type for p in item.app.platforms],
                }
                for item in self.items
            ],
        }


async def _load_candidates(session: AsyncSession, subject: Application) -> list[Application]:
    """Candidate pool: active apps sharing a category or the developer,
    plus a popularity floor to keep the pool small and relevant."""
    query = (
        select(Application)
        .where(
            Application.id != subject.id,
            Application.is_active.is_(True),
            Application.is_deleted.is_(False),
        )
        .options(
            selectinload(Application.categories),
            selectinload(Application.tags),
            selectinload(Application.developer),
            selectinload(Application.organization),
            selectinload(Application.license),
            selectinload(Application.platforms),
        )
    )

    category_ids = [c.id for c in subject.categories]
    subject_developer_id = subject.developer_id
    subject_org_id = subject.organization_id
    subject_tag_ids = {t.id for t in subject.tags}

    clauses = []
    if category_ids:
        clauses.append(Application.categories.any(Category.id.in_(category_ids)))
    ors = []
    if subject_developer_id:
        ors.append(Application.developer_id == subject_developer_id)
    if subject_org_id:
        ors.append(Application.organization_id == subject_org_id)
    if ors:
        clauses.extend(ors)
    if subject_tag_ids:
        clauses.append(Application.tags.any(Tag.id.in_(subject_tag_ids)))

    if clauses:
        query = query.where(*clauses)
    result = await session.execute(
        query.order_by(Application.download_count.desc()).limit(MAX_CANDIDATES)
    )
    return list(result.scalars().unique().all())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _popularity_component(popularity: float | None) -> float:
    """Log-scale the 0-100 popularity score into [0, WEIGHT_POPULARITY]."""
    if popularity is None or popularity <= 0:
        return 0.0
    return WEIGHT_POPULARITY * (math.log1p(popularity) / math.log1p(100.0))


def score_candidate(
    candidate: Application,
    subject: Application,
    popularity: float | None,
) -> tuple[float, dict[str, float], list[str], list[str]]:
    """Score one candidate against the subject app."""
    reasons: dict[str, float] = {}

    subject_categories = {c.slug for c in subject.categories if c.slug}
    candidate_categories = {c.slug for c in candidate.categories if c.slug}
    shared_categories = sorted(subject_categories & candidate_categories)
    if subject.category_id is not None and candidate.category_id is not None:
        subject_primary = next((c for c in subject.categories if c.id == subject.category_id), None)
        candidate_primary = next(
            (c for c in candidate.categories if c.id == candidate.category_id), None
        )
        if subject_primary and candidate_primary and subject_primary.id == candidate_primary.id:
            reasons["shared_category"] = 40.0
        elif shared_categories:
            reasons["shared_category"] = 25.0
    elif shared_categories:
        reasons["shared_category"] = 25.0

    subject_tags = {t.slug for t in subject.tags if t.slug}
    candidate_tags = {t.slug for t in candidate.tags if t.slug}
    shared_tags = sorted(subject_tags & candidate_tags)
    jaccard = _jaccard(subject_tags, candidate_tags)
    if jaccard > 0:
        reasons["shared_tags"] = WEIGHT_TAGS * jaccard

    if (
        subject.developer_id is not None
        and candidate.developer_id is not None
        and subject.developer_id == candidate.developer_id
    ):
        reasons["developer"] = WEIGHT_DEVELOPER
    elif (
        subject.organization_id is not None and candidate.organization_id == subject.organization_id
    ):
        reasons["developer"] = WEIGHT_DEVELOPER * 0.5

    popularity_component = _popularity_component(popularity)
    if popularity_component > 0:
        reasons["popularity"] = popularity_component

    return (
        sum(reasons.values()),
        reasons,
        shared_tags,
        shared_categories,
    )


class RelatedAppsService:
    """Produces explainable related-app recommendations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def related(self, app_id: str, limit: int = 20) -> RelatedAppsResult:
        result = await self.session.execute(
            select(Application).where((Application.app_id == app_id) | (Application.slug == app_id))
        )
        subject = result.scalars().first()
        if subject is None:
            return RelatedAppsResult(subject_app_id=app_id)

        candidates = await _load_candidates(self.session, subject)
        if not candidates:
            return RelatedAppsResult(subject_app_id=subject.app_id)

        popularity_rows = await self.session.execute(
            select(PopularityScore.application_id, PopularityScore.normalized_score).where(
                PopularityScore.application_id.in_([c.id for c in candidates])
            )
        )
        popularity = {row[0]: row[1] for row in popularity_rows.all()}

        scored: list[RelatedApp] = []
        for candidate in candidates:
            total, reasons, shared_tags, shared_categories = score_candidate(
                candidate, subject, popularity.get(candidate.id)
            )
            if total >= MIN_SCORE:
                scored.append(
                    RelatedApp(
                        app=candidate,
                        score=total,
                        reasons=reasons,
                        shared_tags=shared_tags,
                        shared_categories=shared_categories,
                    )
                )
        scored.sort(key=lambda item: item.score, reverse=True)
        return RelatedAppsResult(subject_app_id=subject.app_id, items=scored[:limit])


__all__ = ["RelatedApp", "RelatedAppsResult", "RelatedAppsService", "score_candidate"]
