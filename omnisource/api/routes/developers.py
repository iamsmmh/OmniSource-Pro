"""Developers API routes for OmniSource."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from omnisource.config.logging import get_logger
from omnisource.api.dependencies import get_db
from omnisource.core.models.application import Application
from omnisource.core.models.developer import Developer
from omnisource.core.schemas.developer import DeveloperSchema

logger = get_logger(__name__)

router = APIRouter()


@router.get("", response_model=List[DeveloperSchema])
async def list_developers(
    q: Optional[str] = Query(default=None, description="Search by name"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    session=Depends(get_db),
):
    """List developers with optional search and pagination."""
    try:
        query = select(Developer).order_by(Developer.name.asc())
        if q:
            query = query.where(Developer.name.ilike(f"%{q}%"))
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await session.execute(query)
        return list(result.scalars().all())
    except Exception as e:
        logger.error(f"Failed to list developers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{slug}")
async def get_developer(slug: str, session=Depends(get_db)):
    """Get a single developer by slug."""
    try:
        result = await session.execute(
            select(Developer).where(Developer.slug == slug)
        )
        developer = result.scalar_one_or_none()
        if developer is None:
            raise HTTPException(status_code=404, detail="Developer not found")

        app_count = await session.scalar(
            select(func.count()).select_from(Application).where(
                Application.developer_id == developer.id
            )
        )

        data = DeveloperSchema.model_validate(developer).model_dump()
        data["app_count"] = app_count
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get developer {slug}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
