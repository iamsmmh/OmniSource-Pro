"""
Search API routes for OmniSource.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from omnisource.api.dependencies import get_db
from omnisource.config.logging import get_logger
from omnisource.core.repositories.application import ApplicationRepository
from omnisource.core.schemas.omnistore import PaginatedApps

logger = get_logger(__name__)

router = APIRouter()


@router.get("", response_model=PaginatedApps)
async def search_apps(
    q: str | None = Query(default=None, description="Search query"),
    platform: str | None = Query(default=None, description="Filter by platform"),
    category: str | None = Query(default=None, description="Filter by category"),
    license: str | None = Query(default=None, description="Filter by license"),
    architecture: str | None = Query(default=None, description="Filter by architecture"),
    open_source: str | None = Query(default=None, description="Filter by open source status"),
    min_trust: int | None = Query(default=None, ge=0, le=100, description="Minimum trust score"),
    min_quality: int | None = Query(
        default=None, ge=0, le=100, description="Minimum quality score"
    ),
    updated_since: str | None = Query(
        default=None, description="Only apps updated since this date"
    ),
    sort: str | None = Query(
        default="relevance",
        description="Sort by: relevance, popularity, updated, newest, name, trust",
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=30, ge=1, le=100, description="Items per page"),
    session=Depends(get_db),
) -> PaginatedApps:
    """
    Search applications with full-text search and filtering.
    """
    try:
        repo = ApplicationRepository(session)

        # Build filter parameters
        filters = {
            "q": q,
            "platform": platform,
            "category": category,
            "license": license,
            "architecture": architecture,
            "open_source": open_source,
            "min_trust": str(min_trust) if min_trust else None,
            "min_quality": str(min_quality) if min_quality else None,
            "updated_since": updated_since,
            "sort": sort,
        }

        # Get paginated results
        result = await repo.get_apps_paginated(page=page, per_page=per_page, **filters)

        return result

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
