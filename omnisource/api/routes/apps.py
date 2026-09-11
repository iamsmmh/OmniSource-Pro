"""
Apps API routes for OmniSource.

Provides endpoints for listing and retrieving applications.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from omnisource.api.dependencies import get_db
from omnisource.config.logging import get_logger
from omnisource.core.repositories.application import ApplicationRepository
from omnisource.core.schemas.omnistore import OmniStoreApp, PaginatedApps

logger = get_logger(__name__)

router = APIRouter()


@router.get("", response_model=PaginatedApps)
async def list_apps(
    q: str | None = Query(default=None, description="Search query"),
    platform: str | None = Query(default=None, description="Filter by platform"),
    category: str | None = Query(default=None, description="Filter by category"),
    developer: str | None = Query(default=None, description="Filter by developer id or slug"),
    license: str | None = Query(default=None, description="Filter by license"),
    architecture: str | None = Query(default=None, description="Filter by architecture"),
    open_source: bool | None = Query(default=None, description="Filter by open source status"),
    min_trust: int | None = Query(default=None, ge=0, le=100, description="Minimum trust score"),
    min_quality: int | None = Query(
        default=None, ge=0, le=100, description="Minimum quality score"
    ),
    updated_since: str | None = Query(
        default=None, description="Only apps updated since this date"
    ),
    sort: str | None = Query(
        default=None, description="Sort by: popularity, updated, newest, name, trust"
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=30, ge=1, le=100, description="Items per page"),
    session=Depends(get_db),
) -> PaginatedApps:
    """
    List applications with optional filtering and sorting.

    This endpoint returns a paginated list of applications matching the specified criteria.
    """
    try:
        repo = ApplicationRepository(session)

        # Build filter parameters
        filters = {
            "q": q,
            "platform": platform,
            "category": category,
            "developer": developer,
            "license": license,
            "architecture": architecture,
            "open_source": str(open_source).lower() if open_source is not None else None,
            "min_trust": str(min_trust) if min_trust is not None else None,
            "min_quality": str(min_quality) if min_quality is not None else None,
            "updated_since": updated_since,
            "sort": sort,
        }

        # Get paginated results
        result = await repo.get_apps_paginated(page=page, per_page=per_page, **filters)

        return result

    except Exception as e:
        logger.error(f"Failed to list apps: {e}")
        raise HTTPException(status_code=500, detail="Service temporarily unavailable") from e


@router.get("/{app_id}", response_model=OmniStoreApp)
async def get_app(
    app_id: str,
    session=Depends(get_db),
) -> OmniStoreApp:
    """
    Get a specific application by ID or slug.

    Returns detailed information about a single application.
    """
    try:
        repo = ApplicationRepository(session)
        app = await repo.get_app_by_id_or_slug(app_id)

        if app is None:
            raise HTTPException(status_code=404, detail="Application not found")

        return app

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get app {app_id}: {e}")
        raise HTTPException(status_code=500, detail="Service temporarily unavailable") from e
