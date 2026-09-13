"""Trending API routes for OmniSource (materialized view backed)."""

from fastapi import APIRouter, Depends, HTTPException, Query

from omnisource.api.dependencies import get_db
from omnisource.api.envelope import success
from omnisource.config.logging import get_logger
from omnisource.core.repositories.catalog import CatalogRepository

logger = get_logger(__name__)

router = APIRouter()


@router.get("")
async def trending_apps(
    limit: int = Query(default=30, ge=1, le=100, description="Number of results"),
    session=Depends(get_db),
):
    """Get trending applications ordered by the trending score (materialized view)."""
    try:
        catalog = CatalogRepository(session)
        apps = await catalog.trending(limit=limit)
        return success(
            data={"items": [app.model_dump(mode="json") for app in apps]},
            meta={"view": "mv_trending_apps", "limit": limit},
        )
    except Exception as e:
        logger.error("Failed to get trending apps: %s", e)
        raise HTTPException(status_code=500, detail="Service temporarily unavailable") from e
