"""Public and authenticated OmniStore collection API."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from omnisource.api.dependencies import get_db
from omnisource.api.security import require_omnistore_subject
from omnisource.core.models.application import Application
from omnisource.core.models.experience import Collection, CollectionItem
from omnisource.core.repositories.application import _APP_LOAD_OPTIONS
from omnisource.core.repositories.mappers import to_omnistore_app
from omnisource.core.schemas.experience import (
    CollectionCreate,
    CollectionItemRequest,
    CollectionResponse,
    PaginatedCollections,
)
from omnisource.processing.deduplication import slugify

router = APIRouter()


async def _collection_response(
    session, collection: Collection, include_items: bool
) -> CollectionResponse:
    ordered_items = sorted(collection.items, key=lambda item: (item.sort_order, item.created_at))
    app_ids = [item.application_id for item in ordered_items] if include_items else []
    apps: dict = {}
    if app_ids:
        result = await session.execute(
            select(Application).where(Application.id.in_(app_ids)).options(*_APP_LOAD_OPTIONS)
        )
        apps = {app.id: app for app in result.scalars().unique().all()}
    return CollectionResponse(
        id=str(collection.id),
        slug=collection.slug,
        name=collection.name,
        description=collection.description,
        is_public=collection.is_public,
        item_count=len(collection.items),
        created_at=collection.created_at,
        updated_at=collection.updated_at,
        items=[
            to_omnistore_app(app)
            for item in ordered_items
            if include_items and (app := apps.get(item.application_id)) is not None
        ],
    )


async def _get_collection(session, collection_id: str) -> Collection | None:
    try:
        result = await session.execute(
            select(Collection)
            .where(Collection.id == collection_id)
            .options(selectinload(Collection.items))
        )
    except (ValueError, TypeError):
        return None
    return result.scalar_one_or_none()


async def _app_id(session, identifier: str):
    result = await session.execute(
        select(Application.id).where(
            (Application.app_id == identifier) | (Application.slug == identifier)
        )
    )
    return result.scalar_one_or_none()


@router.get("", response_model=PaginatedCollections)
async def list_public_collections(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    session=Depends(get_db),
) -> PaginatedCollections:
    """Browse public collections without exposing collection ownership."""
    total = int(
        await session.scalar(
            select(func.count()).select_from(Collection).where(Collection.is_public.is_(True))
        )
        or 0
    )
    result = await session.execute(
        select(Collection)
        .where(Collection.is_public.is_(True))
        .order_by(Collection.updated_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .options(selectinload(Collection.items))
    )
    collections = result.scalars().unique().all()
    return PaginatedCollections(
        items=[
            await _collection_response(session, item, include_items=False) for item in collections
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/mine", response_model=PaginatedCollections)
async def list_my_collections(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    subject_hash: str = Depends(require_omnistore_subject),
    session=Depends(get_db),
) -> PaginatedCollections:
    """List all collections owned by the authenticated OmniStore subject."""
    total = int(
        await session.scalar(
            select(func.count())
            .select_from(Collection)
            .where(Collection.subject_hash == subject_hash)
        )
        or 0
    )
    result = await session.execute(
        select(Collection)
        .where(Collection.subject_hash == subject_hash)
        .order_by(Collection.updated_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .options(selectinload(Collection.items))
    )
    collections = result.scalars().unique().all()
    return PaginatedCollections(
        items=[
            await _collection_response(session, item, include_items=False) for item in collections
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
async def create_collection(
    payload: CollectionCreate,
    subject_hash: str = Depends(require_omnistore_subject),
    session=Depends(get_db),
) -> CollectionResponse:
    """Create a collection for the authenticated OmniStore subject."""
    base_slug = slugify(payload.name)[:120] or "collection"
    slug = base_slug
    suffix = 2
    while await session.scalar(
        select(Collection.id).where(
            Collection.subject_hash == subject_hash, Collection.slug == slug
        )
    ):
        slug = f"{base_slug[:115]}-{suffix}"
        suffix += 1
    collection = Collection(
        subject_hash=subject_hash,
        slug=slug,
        name=payload.name,
        description=payload.description,
        is_public=payload.is_public,
    )
    session.add(collection)
    await session.flush()
    return await _collection_response(session, collection, include_items=False)


@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_public_collection(collection_id: str, session=Depends(get_db)) -> CollectionResponse:
    """Get a public collection and its applications."""
    collection = await _get_collection(session, collection_id)
    if collection is None or not collection.is_public:
        raise HTTPException(status_code=404, detail="Collection not found")
    return await _collection_response(session, collection, include_items=True)


@router.post("/{collection_id}/apps", response_model=CollectionResponse)
async def add_collection_item(
    collection_id: str,
    payload: CollectionItemRequest,
    subject_hash: str = Depends(require_omnistore_subject),
    session=Depends(get_db),
) -> CollectionResponse:
    """Add an application to an owned collection idempotently."""
    collection = await _get_collection(session, collection_id)
    if collection is None or collection.subject_hash != subject_hash:
        raise HTTPException(status_code=404, detail="Collection not found")
    app_id = await _app_id(session, payload.app_id)
    if app_id is None:
        raise HTTPException(status_code=404, detail="Application not found")
    exists = await session.scalar(
        select(CollectionItem.id).where(
            CollectionItem.collection_id == collection.id, CollectionItem.application_id == app_id
        )
    )
    if exists is None:
        item = CollectionItem(
            collection_id=collection.id, application_id=app_id, sort_order=payload.sort_order
        )
        session.add(item)
        collection.items.append(item)
        await session.flush()
    return await _collection_response(session, collection, include_items=True)


@router.delete("/{collection_id}/apps/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_collection_item(
    collection_id: str,
    app_id: str,
    subject_hash: str = Depends(require_omnistore_subject),
    session=Depends(get_db),
) -> None:
    """Remove an application from an owned collection."""
    collection = await _get_collection(session, collection_id)
    if collection is None or collection.subject_hash != subject_hash:
        raise HTTPException(status_code=404, detail="Collection not found")
    application_id = await _app_id(session, app_id)
    if application_id is None:
        raise HTTPException(status_code=404, detail="Application not found")
    item = await session.scalar(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection.id,
            CollectionItem.application_id == application_id,
        )
    )
    if item is not None:
        await session.delete(item)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: str,
    subject_hash: str = Depends(require_omnistore_subject),
    session=Depends(get_db),
) -> None:
    """Delete an owned collection."""
    collection = await _get_collection(session, collection_id)
    if collection is None or collection.subject_hash != subject_hash:
        raise HTTPException(status_code=404, detail="Collection not found")
    await session.delete(collection)
