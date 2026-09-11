"""Aggregate-only analytics ingestion and reporting API."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from omnisource.api.dependencies import get_db
from omnisource.api.security import require_api_key, require_omnistore_subject
from omnisource.core.models.application import Application
from omnisource.core.models.experience import AnalyticsEvent, InteractionType
from omnisource.core.schemas.experience import AnalyticsEventRequest, AnalyticsSummary

router = APIRouter()


async def _find_app_id(session, identifier: str | None):
    if not identifier:
        return None
    return await session.scalar(
        select(Application.id).where(
            (Application.app_id == identifier) | (Application.slug == identifier)
        )
    )


@router.post("/events", status_code=202)
async def record_event(
    payload: AnalyticsEventRequest,
    subject_hash: str = Depends(require_omnistore_subject),
    session=Depends(get_db),
) -> dict[str, str]:
    """Accept an allowlisted, pseudonymous event from an authenticated integration."""
    application_id = await _find_app_id(session, payload.app_id)
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
    return {"status": "accepted"}


@router.get("/summary", response_model=AnalyticsSummary, dependencies=[Depends(require_api_key)])
async def analytics_summary(session=Depends(get_db)) -> AnalyticsSummary:
    """Return aggregate counts for dashboards; no user-level analytics are exposed."""

    async def count(event_type: InteractionType | None = None) -> int:
        query = select(func.count()).select_from(AnalyticsEvent)
        if event_type is not None:
            query = query.where(AnalyticsEvent.event_type == event_type)
        return int(await session.scalar(query) or 0)

    return AnalyticsSummary(
        events=await count(),
        favorites=await count(InteractionType.FAVORITE),
        downloads=await count(InteractionType.DOWNLOAD),
        installs=await count(InteractionType.INSTALL),
        views=await count(InteractionType.VIEW),
    )
