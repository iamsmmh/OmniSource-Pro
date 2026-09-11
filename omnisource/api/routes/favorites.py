"""Authenticated OmniStore favorites API."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from omnisource.api.dependencies import get_db
from omnisource.api.security import require_omnistore_subject
from omnisource.core.models.application import Application
from omnisource.core.models.experience import AnalyticsEvent, InteractionType, UserFavorite
from omnisource.core.repositories.application import _APP_LOAD_OPTIONS
from omnisource.core.repositories.mappers import to_omnistore_app
from omnisource.core.schemas.experience import FavoriteRequest, FavoriteResponse, PaginatedFavorites

router = APIRouter()


async def _app_for_identifier(session, identifier: str) -> Application | None:
    result = await session.execute(
        select(Application)
        .where((Application.app_id == identifier) | (Application.slug == identifier))
        .options(*_APP_LOAD_OPTIONS)
    )
    return result.scalars().first()


@router.get("", response_model=PaginatedFavorites)
async def list_favorites(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    subject_hash: str = Depends(require_omnistore_subject),
    session=Depends(get_db),
) -> PaginatedFavorites:
    """List the authenticated OmniStore user's favorites."""
    total = int(
        await session.scalar(
            select(func.count())
            .select_from(UserFavorite)
            .where(UserFavorite.subject_hash == subject_hash)
        )
        or 0
    )
    rows = await session.execute(
        select(UserFavorite)
        .where(UserFavorite.subject_hash == subject_hash)
        .order_by(UserFavorite.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    favorites = rows.scalars().all()
    app_ids = [favorite.application_id for favorite in favorites]
    apps_result = (
        await session.execute(
            select(Application).where(Application.id.in_(app_ids)).options(*_APP_LOAD_OPTIONS)
        )
        if app_ids
        else None
    )
    apps = {app.id: app for app in apps_result.scalars().unique().all()} if apps_result else {}
    return PaginatedFavorites(
        total=total,
        page=page,
        per_page=per_page,
        items=[
            FavoriteResponse(app=to_omnistore_app(app), created_at=favorite.created_at)
            for favorite in favorites
            if (app := apps.get(favorite.application_id)) is not None
        ],
    )


@router.post("", response_model=FavoriteResponse, status_code=status.HTTP_201_CREATED)
async def add_favorite(
    payload: FavoriteRequest,
    subject_hash: str = Depends(require_omnistore_subject),
    session=Depends(get_db),
) -> FavoriteResponse:
    """Add an application to the authenticated user's favorites idempotently."""
    app = await _app_for_identifier(session, payload.app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    result = await session.execute(
        select(UserFavorite).where(
            UserFavorite.subject_hash == subject_hash, UserFavorite.application_id == app.id
        )
    )
    favorite = result.scalar_one_or_none()
    if favorite is None:
        favorite = UserFavorite(subject_hash=subject_hash, application_id=app.id)
        session.add(favorite)
        session.add(
            AnalyticsEvent(
                subject_hash=subject_hash,
                application_id=app.id,
                event_type=InteractionType.FAVORITE,
            )
        )
        await session.flush()
    return FavoriteResponse(app=to_omnistore_app(app), created_at=favorite.created_at)


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(
    app_id: str,
    subject_hash: str = Depends(require_omnistore_subject),
    session=Depends(get_db),
) -> None:
    """Remove an application from the authenticated user's favorites."""
    app = await _app_for_identifier(session, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    result = await session.execute(
        select(UserFavorite).where(
            UserFavorite.subject_hash == subject_hash, UserFavorite.application_id == app.id
        )
    )
    favorite = result.scalar_one_or_none()
    if favorite is not None:
        await session.delete(favorite)
        session.add(
            AnalyticsEvent(
                subject_hash=subject_hash,
                application_id=app.id,
                event_type=InteractionType.UNFAVORITE,
            )
        )
