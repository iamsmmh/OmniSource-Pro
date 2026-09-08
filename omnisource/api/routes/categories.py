"""Categories API routes for OmniSource."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from omnisource.config.logging import get_logger
from omnisource.api.dependencies import get_db
from omnisource.core.models.application import application_categories
from omnisource.core.models.category import Category
from omnisource.core.schemas.category import CategorySchema

logger = get_logger(__name__)

router = APIRouter()


@router.get("", response_model=List[CategorySchema])
async def list_categories(
    active_only: bool = Query(default=True, description="Only active categories"),
    session=Depends(get_db),
):
    """List all categories."""
    try:
        query = select(Category).order_by(Category.sort_order.asc(), Category.name.asc())
        if active_only:
            query = query.where(Category.is_active.is_(True))
        result = await session.execute(query)
        return list(result.scalars().all())
    except Exception as e:
        logger.error(f"Failed to list categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{slug}")
async def get_category(slug: str, session=Depends(get_db)):
    """Get a single category by slug, including app count."""
    try:
        result = await session.execute(
            select(Category).where(Category.slug == slug)
        )
        category = result.scalar_one_or_none()
        if category is None:
            raise HTTPException(status_code=404, detail="Category not found")

        app_count = await session.scalar(
            select(func.count())
            .select_from(application_categories)
            .where(application_categories.c.category_id == category.id)
        )

        data = CategorySchema.model_validate(category).model_dump()
        data["app_count"] = app_count
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get category {slug}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
