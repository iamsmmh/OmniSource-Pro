"""Developers API routes for OmniSource."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from omnisource.api.dependencies import get_db
from omnisource.api.envelope import pagination_envelope, success
from omnisource.config.logging import get_logger
from omnisource.core.models.application import Application
from omnisource.core.models.developer import Developer
from omnisource.core.schemas.developer import DeveloperSchema

logger = get_logger(__name__)

router = APIRouter()


@router.get("")
async def list_developers(
    q: str | None = Query(default=None, description="Search by name"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    session=Depends(get_db),
):
    """List developers with optional search and pagination."""
    try:
        total_query = select(func.count()).select_from(Developer)
        if q:
            total_query = total_query.where(Developer.name.ilike(f"%{q}%"))
        total = int(await session.scalar(total_query) or 0)

        query = select(Developer).order_by(Developer.name.asc())
        if q:
            query = query.where(Developer.name.ilike(f"%{q}%"))
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await session.execute(query)
        developers = list(result.scalars().all())
        return success(
            data={"items": [DeveloperSchema.model_validate(d).model_dump() for d in developers]},
            pagination=pagination_envelope(page, per_page, total),
        )
    except Exception as e:
        logger.error(f"Failed to list developers: {e}")
        raise HTTPException(status_code=500, detail="Service temporarily unavailable") from e


@router.get("/{slug}")
async def get_developer(slug: str, session=Depends(get_db)):
    """Get a single developer by slug."""
    try:
        result = await session.execute(select(Developer).where(Developer.slug == slug))
        developer = result.scalar_one_or_none()
        if developer is None:
            raise HTTPException(status_code=404, detail="Developer not found")

        app_count = await session.scalar(
            select(func.count())
            .select_from(Application)
            .where(Application.developer_id == developer.id)
        )

        data = DeveloperSchema.model_validate(developer).model_dump()
        data["app_count"] = app_count
        return success(data=data, meta={"slug": slug})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get developer {slug}: {e}")
        raise HTTPException(status_code=500, detail="Service temporarily unavailable") from e
