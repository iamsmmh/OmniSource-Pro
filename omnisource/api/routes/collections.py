"""Public and authenticated OmniStore collection API.

All data responses use the standard ``{success, data, meta, pagination}``
envelope.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from omnisource.api.dependencies import get_db
from omnisource.api.envelope import pagination_envelope, success
from omnisource.api.security import require_omnistore_subject
from omnisource.core.models.application import Application
from omnisource.core.models.experience import Collection, CollectionItem
from omnisource.core.repositories.application import _APP_LOAD_OPTIONS
from omnisource.core.repositories.mappers import to_omnistore_app
from omnisource.core.schemas.experience import (
    CollectionCreate,
    CollectionItemRequest,
    CollectionResponse,
)
from omnisource.processing.deduplication import slugify

router = APIRouter()


async def _collection_response(
    session, collection: Collection, include_items: bool
) -> CollectionResponse:
    """Build the collection payload with explicit queries (no lazy loading).

    Counting via SQL keeps fresh objects (right after CREATE) safe under the
    async session, where touching an unloaded relationship would raise
    MissingGreenlet.
    """
    item_count = int(
        await session.scalar(
            select(func.count())
            .select_from(CollectionItem)
            .where(CollectionItem.collection_id == collection.id)
        )
        or 0
    )
    items: list = []
    if include_items:
        result = await session.execute(
            select(CollectionItem)
            .where(CollectionItem.collection_id == collection.id)
            .order_by(CollectionItem.sort_order, CollectionItem.created_at)
        )
        ordered_items = result.scalars().all()
        app_ids = [item.application_id for item in ordered_items]
        apps: dict = {}
        if app_ids:
            apps_result = await session.execute(
                select(Application).where(Application.id.in_(app_ids)).options(*_APP_LOAD_OPTIONS)
            )
            apps = {app.id: app for app in apps_result.scalars().unique().all()}
        items = [
            to_omnistore_app(app)
            for item in ordered_items
            if (app := apps.get(item.application_id)) is not None
        ]
    return CollectionResponse(
        id=str(collection.id),
        slug=collection.slug,
        name=collection.name,
        description=collection.description,
        is_public=collection.is_public,
        item_count=item_count,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
        items=items,
    )


async def _get_collection(session, collection_id: str) -> Collection | None:
    """Fetch a collection by UUID, returning None for non-UUID identifiers."""
    try:
        collection_uuid = uuid.UUID(collection_id)
    except (ValueError, TypeError, AttributeError):
        return None
    result = await session.execute(select(Collection).where(Collection.id == collection_uuid))
    return result.scalar_one_or_none()


async def _app_id(session, identifier: str):
    result = await session.execute(
        select(Application.id).where(
            (Application.app_id == identifier) | (Application.slug == identifier)
        )
    )
    return result.scalar_one_or_none()


@router.get("")
async def list_public_collections(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    session=Depends(get_db),
) -> dict:
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
    )
    collections = result.scalars().unique().all()
    items = [
        (await _collection_response(session, item, include_items=False)).model_dump(mode="json")
        for item in collections
    ]
    return success(data={"items": items}, pagination=pagination_envelope(page, per_page, total))


@router.get("/mine")
async def list_my_collections(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    subject_hash: str = Depends(require_omnistore_subject),
    session=Depends(get_db),
) -> dict:
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
    )
    collections = result.scalars().unique().all()
    items = [
        (await _collection_response(session, item, include_items=False)).model_dump(mode="json")
        for item in collections
    ]
    return success(data={"items": items}, pagination=pagination_envelope(page, per_page, total))


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_collection(
    payload: CollectionCreate,
    subject_hash: str = Depends(require_omnistore_subject),
    session=Depends(get_db),
) -> dict:
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
    return success(
        data=(await _collection_response(session, collection, include_items=False)).model_dump(
            mode="json"
        )
    )


@router.get("/{collection_id}")
async def get_public_collection(collection_id: str, session=Depends(get_db)) -> dict:
    """Get a public collection and its applications."""
    collection = await _get_collection(session, collection_id)
    if collection is None or not collection.is_public:
        raise HTTPException(status_code=404, detail="Collection not found")
    return success(
        data=(await _collection_response(session, collection, include_items=True)).model_dump(
            mode="json"
        )
    )


@router.post("/{collection_id}/apps")
async def add_collection_item(
    collection_id: str,
    payload: CollectionItemRequest,
    subject_hash: str = Depends(require_omnistore_subject),
    session=Depends(get_db),
) -> dict:
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
        await session.flush()
    return success(
        data=(await _collection_response(session, collection, include_items=True)).model_dump(
            mode="json"
        )
    )


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
