"""Recommendation endpoints for OmniStore clients.

* ``GET /api/v1/recommendations``                 - combined graph + collaborative
* ``GET /api/v1/recommendations/similar``         - content-based similarity
* ``GET /api/v1/recommendations/trending``        - catalogue popularity signals
* ``GET /api/v1/recommendations/discover``        - new / popular discovery
* ``GET /api/v1/recommendations/recommended_apps`` - Phase 6 explainable
  recommendations: Shared Category, Shared Tags, Developer Similarity, and
  Popularity Score (see ``omnisource.intelligence.related_apps``).
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from omnisource.api.dependencies import get_db
from omnisource.api.envelope import success
from omnisource.core.schemas.recommendations import RecommendationKind
from omnisource.intelligence.recommendations import RecommendationService
from omnisource.intelligence.related_apps import RelatedAppsService

router = APIRouter()


@router.get("")
async def recommendations(
    app_id: str = Query(..., min_length=1, description="Source application id or slug"),
    limit: int = Query(default=20, ge=1, le=100),
    session=Depends(get_db),
):
    """Return similar and alternative graph recommendations for an application."""
    service = RecommendationService(session)
    result = await service.related(app_id, relationship="all", limit=limit)
    if not result.items and result.subject_app_id == app_id:
        raise HTTPException(status_code=404, detail="Application not found")
    collaborative = await service.collaborative(app_id, limit=limit)
    seen = {item.app.id for item in result.items}
    result.items.extend(item for item in collaborative if item.app.id not in seen)
    result.items = result.items[:limit]
    return success(data=result.model_dump(mode="json"))


@router.get("/similar")
async def similar_apps(
    app_id: str = Query(..., min_length=1, description="Source application id or slug"),
    limit: int = Query(default=20, ge=1, le=100),
    session=Depends(get_db),
):
    """Return content-based similar applications."""
    result = await RecommendationService(session).related(
        app_id, relationship="similar", limit=limit
    )
    if not result.items and result.subject_app_id == app_id:
        raise HTTPException(status_code=404, detail="Application not found")
    return success(data=result.model_dump(mode="json"))


@router.get("/trending")
async def trending_recommendations(
    limit: int = Query(default=20, ge=1, le=100), session=Depends(get_db)
):
    """Return recommendations based on catalogue popularity signals."""
    result = await RecommendationService(session).catalogue(RecommendationKind.TRENDING, limit)
    return success(data=result.model_dump(mode="json"))


@router.get("/discover")
async def discover_recommendations(
    category: str | None = Query(default=None, max_length=100),
    sort: str = Query(default="new", pattern="^(new|popular)$"),
    limit: int = Query(default=20, ge=1, le=100),
    session=Depends(get_db),
):
    """Discover newly added or popular apps, optionally in one category."""
    kind = RecommendationKind.POPULAR if sort == "popular" else RecommendationKind.NEW
    result = await RecommendationService(session).catalogue(kind, limit, category=category)
    return success(data=result.model_dump(mode="json"))


@router.get("/recommended_apps")
async def recommended_apps(
    app_id: str = Query(..., min_length=1, description="Source application id or slug"),
    limit: int = Query(default=20, ge=1, le=100),
    session=Depends(get_db),
):
    """Explainable related-app recommendations.

    Scoring signals (deterministic, per app): shared category (up to 40),
    shared tags Jaccard (up to 30), developer similarity (up to 20), and
    popularity (up to 10). Each item includes its per-signal breakdown.
    """
    service = RelatedAppsService(session)
    result = await service.related(app_id, limit=limit)
    if not result.items and result.subject_app_id == app_id:
        raise HTTPException(status_code=404, detail="Application not found")
    return success(data=result.to_dict())
