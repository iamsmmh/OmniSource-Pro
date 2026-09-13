"""
Search API routes for OmniSource.

Every search is recorded in ``search_events`` (normalized query, result
count, latency) which powers popular queries, trending searches, and
autocompletion suggestions.
"""

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.api.dependencies import get_db
from omnisource.config.logging import get_logger
from omnisource.core.schemas.omnistore import PaginatedApps
from omnisource.intelligence.analytics_service import AnalyticsService
from omnisource.search.service import SearchService

logger = get_logger(__name__)

router = APIRouter()


async def _record_search(
    session: AsyncSession,
    query: str,
    results_count: int,
    took_ms: int,
) -> None:
    try:
        service = AnalyticsService(session)
        await service.record_search(query, results_count=results_count, took_ms=took_ms)
        await session.commit()
    except Exception:
        logger.debug("Search event recording failed", exc_info=True)


@router.get("", response_model=PaginatedApps)
async def search_apps(
    q: str | None = Query(default=None, description="Search query"),
    platform: str | None = Query(default=None, description="Filter by platform"),
    category: str | None = Query(default=None, description="Filter by category"),
    developer: str | None = Query(default=None, description="Filter by developer id or slug"),
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
        description="Sort by: relevance, popularity, updated, newest, name, trust, downloads",
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
    started = time.perf_counter()
    try:
        service = SearchService()
        result, backend = await service.search(
            session,
            q,
            platform=platform,
            category=category,
            developer=developer,
            license_=license,
            architecture=architecture,
            open_source=open_source,
            min_trust=min_trust,
            min_quality=min_quality,
            updated_since=updated_since,
            sort=sort,
            page=page,
            per_page=per_page,
        )
        if backend == "database" and semantic and q:
            result = await rerank_hybrid(session, q, result, per_page)
        await _record_search(
            session, q or "", len(result.items), int((time.perf_counter() - started) * 1000)
        )
        return result

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail="Service temporarily unavailable") from e


@router.get("/suggestions")
async def search_suggestions(
    q: str = Query(..., min_length=1, max_length=200, description="Search query prefix"),
    limit: int = Query(default=10, ge=1, le=25),
    session=Depends(get_db),
) -> dict[str, Any]:
    """Query suggestions: index-backed matches plus popular-query completion."""
    service = SearchService()
    index_suggestions = await service.suggestions(q, limit=limit)
    lower_q = q.strip().lower()

    from omnisource.intelligence.analytics_service import AnalyticsService

    popular = await AnalyticsService(session).popular_queries(days=30, limit=limit)
    popular_matches = [
        {"text": row["query"], "source": "popular"}
        for row in popular
        if lower_q
        and row["query"].startswith(lower_q)
        and row["query"] not in {s["text"].lower() for s in index_suggestions}
    ][:limit]

    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for suggestion in [*index_suggestions, *popular_matches]:
        key = suggestion["text"].lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(suggestion)
        if len(merged) >= limit:
            break
    return {"query": q, "suggestions": merged}


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
