"""Platforms API routes for OmniSource."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from omnisource.api.dependencies import get_db
from omnisource.api.envelope import success
from omnisource.config.logging import get_logger
from omnisource.core.models.platform import Platform
from omnisource.core.schemas.platform import PlatformSchema

logger = get_logger(__name__)

router = APIRouter()


@router.get("")
async def list_platforms(
    active_only: bool = Query(default=True, description="Only active platforms"),
    session=Depends(get_db),
):
    """List all supported platforms."""
    try:
        query = select(Platform).order_by(Platform.name.asc())
        if active_only:
            query = query.where(Platform.is_active.is_(True))
        result = await session.execute(query)
        platforms = list(result.scalars().all())
        return success(
            data={"items": [PlatformSchema.model_validate(p).model_dump() for p in platforms]},
            meta={"count": len(platforms)},
        )
    except Exception as e:
        logger.error(f"Failed to list platforms: {e}")
        raise HTTPException(status_code=500, detail="Service temporarily unavailable") from e


@router.get("/{platform_type}")
async def get_platform(platform_type: str, session=Depends(get_db)):
    """Get a single platform by type."""
    try:
        result = await session.execute(
            select(Platform).where(Platform.platform_type == platform_type)
        )
        platform = result.scalar_one_or_none()
        if platform is None:
            raise HTTPException(status_code=404, detail="Platform not found")
        return success(
            data=PlatformSchema.model_validate(platform).model_dump(),
            meta={"platform_type": platform_type},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get platform {platform_type}: {e}")
        raise HTTPException(status_code=500, detail="Service temporarily unavailable") from e
