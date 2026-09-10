"""Releases API routes for OmniSource."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from omnisource.api.dependencies import get_db
from omnisource.config.logging import get_logger
from omnisource.core.models.release import Release, ReleaseAsset
from omnisource.core.schemas.omnistore import OmniStoreRelease

logger = get_logger(__name__)

router = APIRouter()


@router.get("")
async def list_releases(
    app_id: str | None = Query(default=None, description="Filter by application id"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    session=Depends(get_db),
):
    """List releases with optional filtering and pagination."""
    try:
        filters = []
        if app_id:
            from omnisource.core.models.application import Application

            filters.append(Release.application.has(Application.app_id == app_id))

        total = await session.scalar(select(func.count()).select_from(Release).where(*filters))

        query = (
            select(Release)
            .where(*filters)
            .order_by(Release.published_at.desc().nulls_last())
            .options(selectinload(Release.assets).selectinload(ReleaseAsset.asset))
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await session.execute(query)
        releases = result.scalars().unique().all()

        items = []
        for release in releases:
            items.append(
                OmniStoreRelease(
                    version=release.version,
                    released_at=release.published_at.isoformat() if release.published_at else None,
                    notes=release.body,
                    assets=[],
                ).model_dump()
            )

        return {"items": items, "total": total, "page": page}
    except Exception as e:
        logger.error(f"Failed to list releases: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{release_id}")
async def get_release(release_id: str, session=Depends(get_db)):
    """Get a single release by id or external id."""
    try:
        query = select(Release).where(
            (Release.external_id == release_id) | (Release.id == release_id)
        )
        result = await session.execute(query)
        release = result.scalar_one_or_none()
        if release is None:
            raise HTTPException(status_code=404, detail="Release not found")
        return {
            "version": release.version,
            "tag": release.tag,
            "name": release.name,
            "body": release.body,
            "published_at": release.published_at.isoformat() if release.published_at else None,
            "is_prerelease": release.is_prerelease,
            "is_draft": release.is_draft,
            "download_count": release.download_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get release {release_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
