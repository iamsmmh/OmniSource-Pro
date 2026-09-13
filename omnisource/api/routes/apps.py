"""
Apps API routes for OmniSource.

Endpoints (all using the {success, data, meta, pagination} envelope):

* ``GET /api/v1/apps``                        - filtered, sorted, paginated list
* ``GET /api/v1/apps/featured``               - featured catalogue (materialized view)
* ``GET /api/v1/apps/recent``                 - recently updated (materialized view)
* ``GET /api/v1/apps/most-downloaded``        - most downloaded (materialized view)
* ``GET /api/v1/apps/{app_id}``               - single application detail
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from omnisource.api.dependencies import get_db
from omnisource.api.envelope import pagination_envelope, success
from omnisource.config.logging import get_logger
from omnisource.core.repositories.application import ApplicationRepository
from omnisource.core.repositories.catalog import CatalogRepository

logger = get_logger(__name__)

router = APIRouter()


@router.get("")
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
) -> dict:
    """List applications with optional filtering, sorting, and pagination."""
    try:
        repo = ApplicationRepository(session)
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
        result = await repo.get_apps_paginated(page=page, per_page=per_page, **filters)
        return success(
            data={"items": [app.model_dump(mode="json") for app in result.items]},
            meta={"freshness": result.freshness},
            pagination=pagination_envelope(page, per_page, result.total),
        )
    except Exception as e:
        logger.error("Failed to list apps: %s", e)
        raise HTTPException(status_code=500, detail="Service temporarily unavailable") from e


@router.get("/featured")
async def featured_apps(
    limit: int = Query(default=30, ge=1, le=100),
    session=Depends(get_db),
) -> dict:
    """Featured applications (materialized view ``mv_featured_apps``)."""
    catalog = CatalogRepository(session)
    apps = await catalog.featured(limit=limit)
    return success(data={"items": [app.model_dump(mode="json") for app in apps]})


@router.get("/recent")
async def recently_updated_apps(
    limit: int = Query(default=30, ge=1, le=100),
    session=Depends(get_db),
) -> dict:
    """Recently updated applications (materialized view ``mv_recently_updated_apps``)."""
    catalog = CatalogRepository(session)
    apps = await catalog.recently_updated(limit=limit)
    return success(data={"items": [app.model_dump(mode="json") for app in apps]})


@router.get("/most-downloaded")
async def most_downloaded_apps(
    limit: int = Query(default=30, ge=1, le=100),
    session=Depends(get_db),
) -> dict:
    """Most downloaded applications (materialized view ``mv_most_downloaded_apps``)."""
    catalog = CatalogRepository(session)
    apps = await catalog.most_downloaded(limit=limit)
    return success(data={"items": [app.model_dump(mode="json") for app in apps]})


@router.get("/{app_id}")
async def get_app(app_id: str, session=Depends(get_db)) -> dict:
    """Get a specific application by ID or slug."""
    try:
        repo = ApplicationRepository(session)
        app = await repo.get_app_by_id_or_slug(app_id)
        if app is None:
            raise HTTPException(status_code=404, detail="Application not found")
        return success(
            data=app.model_dump(mode="json"),
            meta={"app_id": app_id, "resolved_id": app.id},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get app %s: %s", app_id, e)
        raise HTTPException(status_code=500, detail="Service temporarily unavailable") from e
