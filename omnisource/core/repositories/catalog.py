"""Catalogue repository: materialized views and derived listings.

PostgreSQL stores the four catalogue views as *materialized* views
(refreshed by the scheduler, the admin API, and migrations); other dialects
(e.g. the SQLite test database) keep the same names as plain views, so the
query code is identical everywhere.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from omnisource.config.logging import get_logger
from omnisource.core.models.application import Application
from omnisource.core.repositories.base import BaseRepository
from omnisource.core.repositories.mappers import to_omnistore_app
from omnisource.core.schemas.omnistore import OmniStoreApp

logger = get_logger(__name__)

VIEW_TRENDING = "mv_trending_apps"
VIEW_FEATURED = "mv_featured_apps"
VIEW_RECENTLY_UPDATED = "mv_recently_updated_apps"
VIEW_MOST_DOWNLOADED = "mv_most_downloaded_apps"

_ALL_VIEWS = (VIEW_TRENDING, VIEW_FEATURED, VIEW_RECENTLY_UPDATED, VIEW_MOST_DOWNLOADED)

# Constant SQL templates (view names never interpolated from user input).
_VIEW_SELECTS = {
    VIEW_TRENDING: (
        "SELECT a.id FROM applications a "
        "JOIN mv_trending_apps v ON v.id = a.id "
        "ORDER BY v.trending_score DESC LIMIT :limit"
    ),
    VIEW_FEATURED: (
        "SELECT a.id FROM applications a "
        "JOIN mv_featured_apps v ON v.id = a.id "
        "ORDER BY v.updated_at DESC LIMIT :limit"
    ),
    VIEW_RECENTLY_UPDATED: (
        "SELECT a.id FROM applications a "
        "JOIN mv_recently_updated_apps v ON v.id = a.id "
        "ORDER BY v.updated_at DESC LIMIT :limit"
    ),
    VIEW_MOST_DOWNLOADED: (
        "SELECT a.id FROM applications a "
        "JOIN mv_most_downloaded_apps v ON v.id = a.id "
        "ORDER BY v.download_count DESC LIMIT :limit"
    ),
}


class CatalogRepository(BaseRepository[Application]):
    """Reads the derived catalogue views and refreshes them on PostgreSQL."""

    model = Application

    async def refresh_materialized_views(self) -> dict[str, Any]:
        """REFRESH MATERIALIZED VIEW ... CONCURRENTLY for each catalogue view.

        No-op (and reported as such) on dialects without materialized views.
        """
        dialect = self.session.bind.dialect.name
        if dialect != "postgresql":
            return {"dialect": dialect, "refreshed": 0, "skipped": True}
        for view in _ALL_VIEWS:
            try:
                await self.session.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}"))
            except Exception as exc:
                # A concurrent refresh can fail when the unique index is
                # missing; fall back to a blocking refresh.
                logger.warning("Concurrent refresh of %s failed (%s); blocking", view, exc)
                await self.session.execute(text(f"REFRESH MATERIALIZED VIEW {view}"))
        await self.session.commit()
        return {"dialect": dialect, "refreshed": len(_ALL_VIEWS)}

    async def _from_view(self, view: str, limit: int) -> list[OmniStoreApp]:
        """Resolve view rows back to full application documents.

        SQL text is selected from a constant table keyed by the view name -
        no identifier is ever interpolated from user input.
        """
        if view not in _VIEW_SELECTS:
            raise ValueError(f"unknown view: {view}")
        result = await self.session.execute(text(_VIEW_SELECTS[view]), {"limit": limit})
        # Raw text() results are untyped: PostgreSQL drivers surface native
        # uuid.UUID objects while SQLite returns the stored hex string.
        # Normalize so the ORM bind below works on every dialect.
        app_ids: list[Any] = []
        for row in result.all():
            raw_id = row[0]
            app_ids.append(uuid.UUID(raw_id) if isinstance(raw_id, str) else raw_id)
        if not app_ids:
            return []

        from sqlalchemy import select

        from omnisource.core.repositories.application import _APP_LOAD_OPTIONS

        rows = (
            (
                await self.session.execute(
                    select(Application)
                    .where(Application.id.in_(app_ids))
                    .options(*_APP_LOAD_OPTIONS)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        by_id = {app.id: app for app in rows}
        apps: list[OmniStoreApp] = []
        for app_id in app_ids:
            app = by_id.get(app_id)
            if app is not None:
                apps.append(to_omnistore_app(app))
        return apps

    async def trending(self, limit: int = 30) -> list[OmniStoreApp]:
        return await self._from_view(VIEW_TRENDING, limit)

    async def featured(self, limit: int = 30) -> list[OmniStoreApp]:
        return await self._from_view(VIEW_FEATURED, limit)

    async def recently_updated(self, limit: int = 30) -> list[OmniStoreApp]:
        return await self._from_view(VIEW_RECENTLY_UPDATED, limit)

    async def most_downloaded(self, limit: int = 30) -> list[OmniStoreApp]:
        return await self._from_view(VIEW_MOST_DOWNLOADED, limit)

    async def explain(self, view: str) -> list[dict[str, Any]]:
        """EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) a top-30 view query.

        Used by the admin API for the query-optimization report.
        """
        if view not in _VIEW_SELECTS:
            raise ValueError(f"unknown view: {view}")
        dialect = self.session.bind.dialect.name
        analyze = (
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)"
            if dialect == "postgresql"
            else "EXPLAIN QUERY PLAN"
        )
        sql = "\n".join((analyze, _VIEW_SELECTS[view].replace(":limit", "30")))
        result = await self.session.execute(text(sql))
        row = result.first()
        if row is None:
            return []
        payload = row[0]
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return [payload]
        return [{"plan": str(payload)}]


__all__ = [
    "VIEW_FEATURED",
    "VIEW_MOST_DOWNLOADED",
    "VIEW_RECENTLY_UPDATED",
    "VIEW_TRENDING",
    "CatalogRepository",
]
