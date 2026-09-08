"""Latest API routes for OmniSource."""

from fastapi import APIRouter, Depends, HTTPException, Query

from omnisource.config.logging import get_logger
from omnisource.api.dependencies import get_db
from omnisource.core.repositories.application import ApplicationRepository
from omnisource.core.schemas.omnistore import OmniStoreApp

logger = get_logger(__name__)

router = APIRouter()


@router.get("", response_model=list[OmniStoreApp])
async def latest_apps(
    limit: int = Query(default=30, ge=1, le=100, description="Number of results"),
    session=Depends(get_db),
):
    """Get the most recently added applications."""
    try:
        repo = ApplicationRepository(session)
        return await repo.get_latest(limit=limit)
    except Exception as e:
        logger.error(f"Failed to get latest apps: {e}")
        raise HTTPException(status_code=500, detail=str(e))
