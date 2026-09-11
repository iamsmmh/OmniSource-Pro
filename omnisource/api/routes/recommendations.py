"""Explainable recommendation endpoints for OmniStore clients."""

from fastapi import APIRouter, Depends, HTTPException, Query

from omnisource.api.dependencies import get_db
from omnisource.core.schemas.recommendations import RecommendationKind, RecommendationResponse
from omnisource.intelligence.recommendations import RecommendationService

router = APIRouter()


@router.get("", response_model=RecommendationResponse)
async def recommendations(
    app_id: str = Query(..., min_length=1, description="Source application id or slug"),
    limit: int = Query(default=20, ge=1, le=100),
    session=Depends(get_db),
) -> RecommendationResponse:
    """Return similar and alternative graph recommendations for an application."""
    service = RecommendationService(session)
    result = await service.related(app_id, relationship="all", limit=limit)
    if not result.items and result.subject_app_id == app_id:
        raise HTTPException(status_code=404, detail="Application not found")
    collaborative = await service.collaborative(app_id, limit=limit)
    seen = {item.app.id for item in result.items}
    result.items.extend(item for item in collaborative if item.app.id not in seen)
    result.items = result.items[:limit]
    return result


@router.get("/similar", response_model=RecommendationResponse)
async def similar_apps(
    app_id: str = Query(..., min_length=1, description="Source application id or slug"),
    limit: int = Query(default=20, ge=1, le=100),
    session=Depends(get_db),
) -> RecommendationResponse:
    """Return content-based similar applications."""
    result = await RecommendationService(session).related(
        app_id, relationship="similar", limit=limit
    )
    if not result.items and result.subject_app_id == app_id:
        raise HTTPException(status_code=404, detail="Application not found")
    return result


@router.get("/trending", response_model=RecommendationResponse)
async def trending_recommendations(
    limit: int = Query(default=20, ge=1, le=100), session=Depends(get_db)
) -> RecommendationResponse:
    """Return recommendations based on catalogue popularity signals."""
    return await RecommendationService(session).catalogue(RecommendationKind.TRENDING, limit)


@router.get("/discover", response_model=RecommendationResponse)
async def discover_recommendations(
    category: str | None = Query(default=None, max_length=100),
    sort: str = Query(default="new", pattern="^(new|popular)$"),
    limit: int = Query(default=20, ge=1, le=100),
    session=Depends(get_db),
) -> RecommendationResponse:
    """Discover newly added or popular apps, optionally in one category."""
    kind = RecommendationKind.POPULAR if sort == "popular" else RecommendationKind.NEW
    return await RecommendationService(session).catalogue(kind, limit, category=category)
