"""
Search API routes for OmniSource.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from omnisource.config.logging import get_logger
from omnisource.core.schemas.omnistore import OmniStoreApp, PaginatedApps
from omnisource.core.repositories.application import ApplicationRepository
from omnisource.api.dependencies import get_db

logger = get_logger(__name__)

router = APIRouter()


@router.get("", response_model=PaginatedApps)
async def search_apps(
    q: Optional[str] = Query(default=None, description="Search query"),
    platform: Optional[str] = Query(default=None, description="Filter by platform"),
    category: Optional[str] = Query(default=None, description="Filter by category"),
    license: Optional[str] = Query(default=None, description="Filter by license"),
    architecture: Optional[str] = Query(default=None, description="Filter by architecture"),
    open_source: Optional[str] = Query(default=None, description="Filter by open source status"),
    min_trust: Optional[int] = Query(default=None, ge=0, le=100, description="Minimum trust score"),
    min_quality: Optional[int] = Query(default=None, ge=0, le=100, description="Minimum quality score"),
    updated_since: Optional[str] = Query(default=None, description="Only apps updated since this date"),
    sort: Optional[str] = Query(
        default="relevance",
        description="Sort by: relevance, popularity, updated, newest, name, trust"
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
        result = await repo.get_apps_paginated(
            page=page,
            per_page=per_page,
            **filters
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
