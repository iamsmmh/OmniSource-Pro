"""Statistics API routes for OmniSource."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from omnisource.api.dependencies import get_db
from omnisource.config.logging import get_logger
from omnisource.core.models.application import Application
from omnisource.core.models.asset import Asset
from omnisource.core.models.category import Category
from omnisource.core.models.platform import Platform
from omnisource.core.models.release import Release
from omnisource.core.models.repository import Repository
from omnisource.core.models.source import Source

logger = get_logger(__name__)

router = APIRouter()


@router.get("")
async def stats(session=Depends(get_db)):
    """Return catalog-wide statistics."""
    try:

        async def _count(model, *filters):
            return int(
                await session.scalar(select(func.count()).select_from(model).where(*filters))
            )

        return {
            "applications": await _count(Application, Application.is_active.is_(True)),
            "repositories": await _count(Repository),
            "releases": await _count(Release),
            "assets": await _count(Asset),
            "sources": await _count(Source, Source.is_active.is_(True)),
            "platforms": await _count(Platform),
            "categories": await _count(Category),
            "total_apps": await _count(Application),
            "total_downloads": await session.scalar(
                select(func.coalesce(func.sum(Release.download_count), 0)).select_from(Release)
            ),
        }
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
