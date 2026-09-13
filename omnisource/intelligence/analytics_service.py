"""Analytics ingestion and aggregation.

Ingestion writes into the dedicated event tables (``download_events``,
``view_events``, ``search_events``) and increments the denormalized
``applications.download_count`` counter so the trending / most-downloaded
materialized views stay current without scanning raw events on every read.

All reporting endpoints return aggregates only - no user-level data leaves
the service (``subject_hash`` is an internal pseudonym and is never
exposed).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.core.models.analytics import DownloadEvent, SearchEvent, ViewEvent
from omnisource.core.models.application import Application

logger = get_logger(__name__)

_QUERY_CLEAN = re.compile(r"\s+")


def normalize_query(text: str) -> str:
    """Lowercase, trim, and collapse whitespace in a search query."""
    return _QUERY_CLEAN.sub(" ", text.strip().lower())[:300]


class AnalyticsService:
    """Read/write access to analytics events and aggregates."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    async def record_download(
        self,
        application_id: Any | None,
        *,
        subject_hash: str | None = None,
        platform: str | None = None,
        country: str | None = None,
        user_agent: str | None = None,
        referrer: str | None = None,
        version: str | None = None,
        client_info: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        """Record one download and increment the application counter."""
        event = DownloadEvent(
            occurred_at=occurred_at or datetime.now(UTC),
            application_id=application_id,
            subject_hash=subject_hash,
            platform=platform,
            country=_clean_country(country),
            user_agent=(user_agent or "")[:255] or None,
            referrer=(referrer or "")[:500] or None,
            version=(version or "")[:50] or None,
            client_info=client_info or {},
        )
        self.session.add(event)
        if application_id is not None:
            await self._bump_download_count(application_id)

    async def record_view(
        self,
        application_id: Any | None,
        *,
        subject_hash: str | None = None,
        platform: str | None = None,
        country: str | None = None,
        user_agent: str | None = None,
        referrer: str | None = None,
        client_info: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        self.session.add(
            ViewEvent(
                occurred_at=occurred_at or datetime.now(UTC),
                application_id=application_id,
                subject_hash=subject_hash,
                platform=platform,
                country=_clean_country(country),
                user_agent=(user_agent or "")[:255] or None,
                referrer=(referrer or "")[:500] or None,
                version=None,
                client_info=client_info or {},
            )
        )

    async def record_search(
        self,
        query_text: str,
        *,
        application_id: Any | None = None,
        results_count: int = 0,
        took_ms: int | None = None,
        country: str | None = None,
        platform: str | None = None,
        user_agent: str | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        self.session.add(
            SearchEvent(
                occurred_at=occurred_at or datetime.now(UTC),
                application_id=application_id,
                subject_hash=None,
                platform=platform,
                country=_clean_country(country),
                user_agent=(user_agent or "")[:255] or None,
                query_text=normalize_query(query_text),
                results_count=int(results_count or 0),
                took_ms=took_ms,
                client_info={},
            )
        )

    async def _bump_download_count(self, application_id: Any) -> None:
        result = await self.session.execute(
            select(Application).where(Application.id == application_id)
        )
        app = result.scalars().first()
        if app is not None:
            app.download_count = (app.download_count or 0) + 1

    # ------------------------------------------------------------------
    # Aggregates
    # ------------------------------------------------------------------

    async def summary(self, since: datetime | None = None) -> dict[str, Any]:
        """Total event counts by type."""

        def _count(model: Any, since: datetime | None) -> Any:
            query = select(func.count()).select_from(model)
            if since is not None:
                query = query.where(model.occurred_at >= since)
            return query

        downloads = await self.session.scalar(_count(DownloadEvent, since))
        views = await self.session.scalar(_count(ViewEvent, since))
        searches = await self.session.scalar(_count(SearchEvent, since))
        return {
            "downloads": int(downloads or 0),
            "views": int(views or 0),
            "searches": int(searches or 0),
        }

    async def timeseries(
        self,
        days: int = 30,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        """Daily buckets of downloads, views, and searches for the last N days."""
        since = since or (datetime.now(UTC) - timedelta(days=days))
        buckets: dict[str, dict[str, int]] = {}

        def _day(ts: datetime) -> str:
            return ts.astimezone(UTC).date().isoformat()

        for model, key in (
            (DownloadEvent, "downloads"),
            (ViewEvent, "views"),
            (SearchEvent, "searches"),
        ):
            query = (
                select(model.occurred_at, func.count())
                .where(model.occurred_at >= since)
                .group_by(func.date(model.occurred_at))
            )
            result = await self.session.execute(query)
            for day_value, count in result.all():
                day = _day(day_value) if isinstance(day_value, datetime) else str(day_value)[:10]
                buckets.setdefault(day, {"downloads": 0, "views": 0, "searches": 0})
                buckets[day][key] = int(count)

        # Fill missing days so clients get a continuous series.
        series = []
        cursor = since.astimezone(UTC).date()
        end = datetime.now(UTC).date()
        while cursor <= end:
            day = cursor.isoformat()
            series.append(
                {
                    "day": day,
                    "downloads": buckets.get(day, {}).get("downloads", 0),
                    "views": buckets.get(day, {}).get("views", 0),
                    "searches": buckets.get(day, {}).get("searches", 0),
                }
            )
            cursor += timedelta(days=1)
        return {"days": days, "series": series}

    async def top_countries(
        self, days: int = 30, limit: int = 10, event: str = "downloads"
    ) -> list[dict[str, Any]]:
        """Top countries by event count."""
        models = {"downloads": DownloadEvent, "views": ViewEvent, "searches": SearchEvent}
        model = models.get(event, DownloadEvent)
        since = datetime.now(UTC) - timedelta(days=days)
        query = (
            select(model.country, func.count().label("count"))
            .where(model.country.isnot(None), model.occurred_at >= since)
            .group_by(model.country)
            .order_by(func.count().desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return [{"country": row[0], "count": int(row[1])} for row in result.all()]

    async def top_downloaded_apps(
        self,
        days: int = 7,
        limit: int = 30,
        platform: str | None = None,
        country: str | None = None,
    ) -> list[dict[str, Any]]:
        """Applications with the most downloads inside the window.

        Falls back to the cumulative ``download_count`` for apps with no
        recent events so the endpoint is useful on a fresh deployment.
        """
        since = datetime.now(UTC) - timedelta(days=days)
        event_query = select(
            DownloadEvent.application_id,
            func.count().label("recent_downloads"),
        ).where(DownloadEvent.application_id.isnot(None), DownloadEvent.occurred_at >= since)
        if platform:
            event_query = event_query.where(DownloadEvent.platform == platform)
        if country:
            event_query = event_query.where(DownloadEvent.country == country)
        app_ids: list[Any] = []
        recent: dict[Any, int] = {}
        result = await self.session.execute(event_query.group_by(DownloadEvent.application_id))
        for row in result.all():
            app_ids.append(row[0])
            recent[row[0]] = int(row[1])

        rows: list[dict[str, Any]] = []
        if app_ids:
            app_query = (
                select(Application)
                .where(
                    Application.id.in_(app_ids),
                    Application.is_active.is_(True),
                    Application.is_deleted.is_(False),
                )
                .order_by(Application.download_count.desc())
                .limit(limit)
            )
            for app in (await self.session.execute(app_query)).scalars().all():
                rows.append(
                    {
                        "app_id": app.app_id,
                        "slug": app.slug,
                        "name": app.name,
                        "recent_downloads": recent.get(app.id, 0),
                        "total_downloads": int(app.download_count or 0),
                    }
                )
        rows.sort(key=lambda row: (row["recent_downloads"], row["total_downloads"]), reverse=True)
        return rows[:limit]

    async def popular_queries(self, days: int = 14, limit: int = 20) -> list[dict[str, Any]]:
        """Most frequent search queries (normalized) in the window."""
        since = datetime.now(UTC) - timedelta(days=days)
        query = (
            select(
                SearchEvent.query_text,
                func.count().label("count"),
                func.avg(SearchEvent.results_count).label("avg_results"),
            )
            .where(SearchEvent.occurred_at >= since, SearchEvent.query_text != "")
            .group_by(SearchEvent.query_text)
            .order_by(func.count().desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return [
            {"query": row[0], "count": int(row[1]), "avg_results": round(float(row[2] or 0), 2)}
            for row in result.all()
        ]

    async def trending_searches(self, limit: int = 20) -> list[dict[str, Any]]:
        """Queries whose frequency is growing: last 7 days vs the prior 7."""
        now = datetime.now(UTC)
        recent_since = now - timedelta(days=7)
        prior_since = now - timedelta(days=14)
        recent = await self.session.execute(
            select(SearchEvent.query_text, func.count())
            .where(SearchEvent.occurred_at >= recent_since)
            .group_by(SearchEvent.query_text)
        )
        prior = await self.session.execute(
            select(SearchEvent.query_text, func.count())
            .where(SearchEvent.occurred_at >= prior_since, SearchEvent.occurred_at < recent_since)
            .group_by(SearchEvent.query_text)
        )
        recent_counts = {row[0]: int(row[1]) for row in recent.all()}
        prior_counts = {row[0]: int(row[1]) for row in prior.all()}
        scored = [
            {
                "query": q,
                "recent": recent_counts.get(q, 0),
                "prior": prior_counts.get(q, 0),
                "growth": (
                    (recent_counts.get(q, 0) - prior_counts.get(q, 0))
                    / max(1, prior_counts.get(q, 0))
                ),
            }
            for q in set(recent_counts) | set(prior_counts)
            if recent_counts.get(q, 0) >= 2
        ]
        scored.sort(key=lambda row: (row["growth"], row["recent"]), reverse=True)
        return scored[:limit]


def _clean_country(country: str | None) -> str | None:
    if not country:
        return None
    cleaned = country.strip().upper()[:2]
    return cleaned if len(cleaned) == 2 and cleaned.isalpha() else None


__all__ = ["AnalyticsService", "normalize_query"]
