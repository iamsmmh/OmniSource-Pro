"""
Search API routes for OmniSource.
"""

from typing import Any

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
    semantic: bool = Query(
        default=False,
        description="Blend embedding similarity into the ranking (requires configured AI provider)",
    ),
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

        # Semantic re-ranking fetches a wider candidate pool first.
        effective_per_page = per_page * 3 if semantic else per_page
        result = await repo.get_apps_paginated(page=page, per_page=effective_per_page, **filters)

        if semantic and q:
            result = await rerank_hybrid(session, q, result, per_page)

        return result

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


async def rerank_hybrid(
    session: Any, query: str, result: PaginatedApps, per_page: int
) -> PaginatedApps:
    """Blend stored-embedding similarity with keyword ranking (RRF)."""
    from omnisource.search.semantic import (
        EmbeddingProvider,
        cosine_similarity,
        get_stored_embeddings,
        hybrid_merge,
    )

    provider = EmbeddingProvider()
    if not provider.available:
        return result  # semantic requires a configured AI provider

    embedded = await provider.embed_texts([query])
    if not embedded or not embedded[0]:
        return result
    query_vector = embedded[0]

    app_ids = [app.id for app in result.items]
    stored = await get_stored_embeddings(session, app_ids)
    if not stored:
        return result

    # Order candidates by cosine similarity to the query vector.
    similarity_pairs: list[tuple[str, int]] = []
    for rank, (app_id, _vector) in enumerate(
        sorted(stored.items(), key=lambda kv: -cosine_similarity(query_vector, kv[1]))
    ):
        similarity_pairs.append((app_id, rank))

    keyword_pairs = [(app.id, rank) for rank, app in enumerate(result.items)]
    merged_ids = set(hybrid_merge(keyword_pairs, similarity_pairs))
    items_by_id = {app.id: app for app in result.items}
    merged = [
        items_by_id[app_id]
        for app_id in hybrid_merge(keyword_pairs, similarity_pairs)
        if app_id in items_by_id
    ]
    # keep only merged items; drop any keyword-only extras beyond the merged set
    merged = [app for app in merged if app.id in merged_ids]
    result.items = merged[:per_page]
    return result
