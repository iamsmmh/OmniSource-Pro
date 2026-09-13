"""Popular applications API (Phase 5 analytics read path)."""

from fastapi import APIRouter, Depends, HTTPException, Query

from omnisource.api.dependencies import get_db
from omnisource.api.envelope import success
from omnisource.config.logging import get_logger
from omnisource.intelligence.analytics_service import AnalyticsService

logger = get_logger(__name__)

router = APIRouter()


@router.get("")
async def popular_apps(
    days: int = Query(default=7, ge=1, le=365, description="Window in days"),
    platform: str | None = Query(default=None, description="Filter by platform"),
    country: str | None = Query(default=None, max_length=2, description="Filter by ISO country"),
    limit: int = Query(default=30, ge=1, le=100),
    session=Depends(get_db),
):
    """Most popular applications by download events inside the window."""
    try:
        service = AnalyticsService(session)
        apps = await service.top_downloaded_apps(
            days=days, limit=limit, platform=platform, country=country
        )
        return success(
            data={"items": apps},
            meta={"window_days": days, "platform": platform, "country": country},
            pagination={"limit": limit, "returned": len(apps)},
        )
    except Exception as e:
        logger.error("Failed to compute popular apps: %s", e)
        raise HTTPException(status_code=500, detail="Service temporarily unavailable") from e
