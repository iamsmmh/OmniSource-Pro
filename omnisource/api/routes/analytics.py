"""Analytics API (Phase 5).

Write path (API-key protected):

* ``POST /api/v1/analytics/ingest`` - bulk record of downloads / views /
  searches; increments ``applications.download_count`` and (on the next
  materialized-view refresh) feeds trending.

Read path (aggregates only, no user-level data):

* ``GET /api/v1/analytics/summary``
* ``GET /api/v1/analytics/timeseries``
* ``GET /api/v1/analytics/countries``
* ``GET /api/v1/analytics/popular-queries``
* ``GET /api/v1/analytics/trending-searches``
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from omnisource.api.dependencies import get_db
from omnisource.api.envelope import success
from omnisource.api.security import require_api_key, require_omnistore_subject
from omnisource.config.logging import get_logger
from omnisource.core.schemas.experience import AnalyticsEventRequest
from omnisource.intelligence.analytics_service import AnalyticsService

logger = get_logger(__name__)

router = APIRouter()

INGEST_BATCH_LIMIT = 1000


@router.post("/events", status_code=202)
async def record_event(
    payload: AnalyticsEventRequest,
    subject_hash: str = Depends(require_omnistore_subject),
    session=Depends(get_db),
):
    """Legacy OmniStore event endpoint (pseudonymous, allowlisted types).

    Kept for backwards compatibility; new clients should use ``/ingest``.
    """
    from omnisource.core.models.application import Application
    from omnisource.core.models.experience import AnalyticsEvent, InteractionType

    async def _find_app_id(identifier: str | None):
        if not identifier:
            return None
        return await session.scalar(
            select(Application.id).where(
                (Application.app_id == identifier) | (Application.slug == identifier)
            )
        )

    application_id = await _find_app_id(payload.app_id)
    if payload.app_id and application_id is None:
        raise HTTPException(status_code=404, detail="Application not found")
    event = AnalyticsEvent(
        subject_hash=subject_hash,
        application_id=application_id,
        event_type=InteractionType(payload.event_type.value),
        platform=payload.platform,
        dimensions=payload.dimensions,
    )
    session.add(event)
    await session.flush()
    await session.commit()
    return {"status": "accepted"}


def _clean_str(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()[:max_length]
    return text or None


@router.post("/ingest", status_code=202)
async def ingest_events(
    payload: dict[str, Any],
    request: Request,
    session=Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """Bulk-ingest analytics events.

    Body::

        {
          "downloads": [{"app_id": "...", "platform": "...", "country": "US",
                          "subject_hash": "...", "occurred_at": "..."}],
          "views":     [{"app_id": "...", ...}],
          "searches":  [{"query": "...", "results_count": 3, ...}]
        }

    ``app_id`` values resolve by application id or slug.
    """
    service = AnalyticsService(session)
    counts = {"downloads": 0, "views": 0, "searches": 0, "ignored": 0}

    def _resolve_app_id(value: Any):
        if not value:
            return None
        # Resolved eagerly below via a single lookup map.
        return str(value)

    raw_downloads = (payload.get("downloads") or [])[:INGEST_BATCH_LIMIT]
    raw_views = (payload.get("views") or [])[:INGEST_BATCH_LIMIT]
    raw_searches = (payload.get("searches") or [])[:INGEST_BATCH_LIMIT]

    ids_needed = {
        _resolve_app_id(event.get("app_id"))
        for event in [*raw_downloads, *raw_views]
        if _resolve_app_id(event.get("app_id"))
    }
    from sqlalchemy import select

    from omnisource.core.models.application import Application

    app_ids: dict[str, Any] = {}
    if ids_needed:
        rows = (
            (
                await session.execute(
                    select(Application).where(
                        (Application.app_id.in_(ids_needed)) | (Application.slug.in_(ids_needed))
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            app_ids[row.app_id] = row.id
            app_ids[row.slug] = row.id

    client_user_agent = _clean_str(request.headers.get("User-Agent"), 255)

    for event in raw_downloads:
        app_id = app_ids.get(str(event.get("app_id") or ""))
        if app_id is None:
            counts["ignored"] += 1
            continue
        await service.record_download(
            app_id,
            subject_hash=_clean_str(event.get("subject_hash"), 64),
            platform=_clean_str(event.get("platform"), 40),
            country=_clean_str(event.get("country"), 2),
            user_agent=_clean_str(event.get("user_agent"), 255) or client_user_agent,
            referrer=_clean_str(event.get("referrer"), 500),
            version=_clean_str(event.get("version"), 50),
            client_info=event.get("client_info")
            if isinstance(event.get("client_info"), dict)
            else {},
            occurred_at=_parse_time(event.get("occurred_at")),
        )
        counts["downloads"] += 1

    for event in raw_views:
        app_id = app_ids.get(str(event.get("app_id") or ""))
        if app_id is None:
            counts["ignored"] += 1
            continue
        await service.record_view(
            app_id,
            subject_hash=_clean_str(event.get("subject_hash"), 64),
            platform=_clean_str(event.get("platform"), 40),
            country=_clean_str(event.get("country"), 2),
            user_agent=_clean_str(event.get("user_agent"), 255) or client_user_agent,
            referrer=_clean_str(event.get("referrer"), 500),
            client_info=event.get("client_info")
            if isinstance(event.get("client_info"), dict)
            else {},
            occurred_at=_parse_time(event.get("occurred_at")),
        )
        counts["views"] += 1

    for event in raw_searches:
        query = _clean_str(event.get("query"), 300)
        if not query:
            counts["ignored"] += 1
            continue
        await service.record_search(
            query,
            results_count=int(event.get("results_count") or 0),
            took_ms=_clean_int(event.get("took_ms")),
            country=_clean_str(event.get("country"), 2),
            platform=_clean_str(event.get("platform"), 40),
            user_agent=_clean_str(event.get("user_agent"), 255) or client_user_agent,
            occurred_at=_parse_time(event.get("occurred_at")),
        )
        counts["searches"] += 1

    await session.commit()
    return success(data={"recorded": counts}, meta={"note": "events accepted for processing"})


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _clean_int(value: Any) -> int | None:
    try:
        number = int(value)
        return number if number >= 0 else None
    except (TypeError, ValueError):
        return None


@router.get("/summary")
async def analytics_summary(
    days: int = Query(default=30, ge=1, le=365),
    session=Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """Total event counts by type over the window."""
    from datetime import UTC, timedelta

    since = datetime.now(UTC) - timedelta(days=days)
    data = await AnalyticsService(session).summary(since=since)
    data["window_days"] = days
    return success(data=data, meta={"window_days": days})


@router.get("/timeseries")
async def analytics_timeseries(
    days: int = Query(default=30, ge=1, le=365),
    session=Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """Daily downloads / views / searches for the window."""
    data = await AnalyticsService(session).timeseries(days=days)
    return success(data=data)


@router.get("/countries")
async def analytics_countries(
    event: str = Query(default="downloads", pattern="^(downloads|views|searches)$"),
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=10, ge=1, le=50),
    session=Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """Top countries by event count (ISO codes, no precise locations)."""
    data = await AnalyticsService(session).top_countries(days=days, limit=limit, event=event)
    return success(data={"items": data, "event": event, "window_days": days})


@router.get("/popular-queries")
async def popular_queries(
    days: int = Query(default=14, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    session=Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """Most frequent search queries (normalized) in the window."""
    data = await AnalyticsService(session).popular_queries(days=days, limit=limit)
    return success(data={"items": data, "window_days": days})


@router.get("/trending-searches")
async def trending_searches(
    limit: int = Query(default=20, ge=1, le=100),
    session=Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """Search queries whose frequency is growing (7d vs prior 7d)."""
    data = await AnalyticsService(session).trending_searches(limit=limit)
    return success(data={"items": data})
