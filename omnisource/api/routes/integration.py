"""Compatibility aliases for the OmniStore Pro integration contract.

The canonical collection endpoints remain plural under ``/api/v1``.  These
singular aliases intentionally preserve the paths used by the existing mobile
and desktop clients without duplicating persistence or response mapping logic.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from omnisource.api.dependencies import get_db
from omnisource.core.models.developer import Developer
from omnisource.core.repositories.application import ApplicationRepository
from omnisource.core.schemas.developer import DeveloperSchema
from omnisource.core.schemas.omnistore import OmniStoreApp

router = APIRouter()


@router.get("/app/{app_id}", response_model=OmniStoreApp)
async def get_app_compat(app_id: str, session=Depends(get_db)) -> OmniStoreApp:
    """Compatibility alias for ``GET /api/v1/apps/{app_id}``."""
    app = await ApplicationRepository(session).get_app_by_id_or_slug(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.get("/developer/{developer_id}")
async def get_developer_compat(
    developer_id: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    session=Depends(get_db),
) -> dict:
    """Return a developer profile and their paginated OmniStore app records."""
    result = await session.execute(
        select(Developer).where(
            (Developer.developer_id == developer_id) | (Developer.slug == developer_id)
        )
    )
    developer = result.scalar_one_or_none()
    if developer is None:
        raise HTTPException(status_code=404, detail="Developer not found")
    apps = await ApplicationRepository(session).get_apps_paginated(
        page=page,
        per_page=per_page,
        developer=developer_id,
    )
    return {
        "developer": DeveloperSchema.model_validate(developer).model_dump(mode="json"),
        "apps": apps.model_dump(mode="json"),
    }
