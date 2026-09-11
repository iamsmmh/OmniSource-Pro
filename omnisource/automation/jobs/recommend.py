"""Bounded background refresh of the persisted recommendation graph."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.core.models.application import Application
from omnisource.intelligence.recommendations import RecommendationService


async def run_recommendation_refresh(
    session: AsyncSession, limit: int = 500, **kwargs: Any
) -> dict[str, int]:
    """Refresh at most ``limit`` active applications per worker invocation."""
    rows = await session.execute(
        select(Application.app_id)
        .where(Application.is_active.is_(True), Application.is_deleted.is_(False))
        .order_by(Application.updated_at.desc())
        .limit(limit)
    )
    service = RecommendationService(session)
    edges = 0
    apps = 0
    for app_id in rows.scalars():
        edges += await service.rebuild_for_app(app_id)
        apps += 1
    return {"applications": apps, "edges": edges}
