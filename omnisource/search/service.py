"""Hybrid search service: Meilisearch-first, database fallback.

Routing rules (deterministic, per request):

* no query text                      -> PostgreSQL (filtered listing)
* query text + unsupported filters   -> PostgreSQL (trust/quality/updated_since)
* query text + supported filters     -> Meilisearch, falling back to
  PostgreSQL when the search engine is unreachable or returns invalid docs

Every executed search is recorded in ``search_events`` (popular/trending
queries) and observed by the search latency metric.
"""

from __future__ import annotations

import time
from typing import Any

from omnisource.api.metrics import SEARCH_DURATION, SEARCH_RESULTS
from omnisource.config.logging import get_logger
from omnisource.core.repositories.application import ApplicationRepository
from omnisource.core.schemas.omnistore import OmniStoreApp, PaginatedApps
from omnisource.search.indexer import NullSearchIndexer, SearchIndexer, get_indexer

logger = get_logger(__name__)

# Filters Meilisearch can express (see indexer settings). Anything else
# routes the request to PostgreSQL.
_MEILI_FILTERS = {"platform", "category", "developer", "license", "open_source"}

_SORT_MAP = {
    "popularity": "scores.popularity:desc",
    "updated": "updated_at:desc",
    "newest": "updated_at:desc",
    "name": "name:asc",
    "trust": "scores.trust:desc",
    "downloads": "download_count:desc",
}


def _meili_filters(
    platform: str | None,
    category: str | None,
    developer: str | None,
    license_: str | None,
    open_source: str | None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if platform:
        filters["platforms"] = platform
    if category:
        filters["categories"] = category
    if developer:
        filters["developer"] = developer
    if license_:
        filters["license"] = license_
    if open_source:
        filters["open_source"] = open_source.lower() in {"true", "1", "yes"}
    return filters


def _meili_sort(sort: str | None) -> list[str] | None:
    if not sort or sort == "relevance":
        return None
    mapped = _SORT_MAP.get(sort)
    return [mapped] if mapped else None


class SearchService:
    """Searches applications and records query analytics."""

    def __init__(self, indexer: SearchIndexer | None = None) -> None:
        self._indexer = indexer

    @property
    def indexer(self) -> SearchIndexer:
        if self._indexer is None:
            self._indexer = get_indexer()
        return self._indexer

    async def search(
        self,
        session: Any,
        q: str | None,
        *,
        platform: str | None = None,
        category: str | None = None,
        developer: str | None = None,
        license_: str | None = None,
        architecture: str | None = None,
        open_source: str | None = None,
        min_trust: int | None = None,
        min_quality: int | None = None,
        updated_since: str | None = None,
        sort: str | None = "relevance",
        page: int = 1,
        per_page: int = 30,
    ) -> tuple[PaginatedApps, str]:
        """Run a search; returns (results, backend) where backend is
        ``meilisearch`` or ``database``."""
        started = time.perf_counter()
        backend = "database"
        result: PaginatedApps | None = None

        can_use_meili = (
            q
            and q.strip()
            and not isinstance(self.indexer, NullSearchIndexer)
            and architecture is None
            and min_trust is None
            and min_quality is None
            and updated_since is None
        )

        if can_use_meili and q is not None:
            try:
                result = self._meili_search(
                    q,
                    platform=platform,
                    category=category,
                    developer=developer,
                    license_=license_,
                    open_source=open_source,
                    sort=sort,
                    page=page,
                    per_page=per_page,
                )
                backend = "meilisearch"
            except Exception as exc:
                logger.warning("Meilisearch search failed; falling back to database: %s", exc)
                result = None

        if result is None:
            repo = ApplicationRepository(session)
            result = await repo.get_apps_paginated(
                page=page,
                per_page=per_page,
                q=q,
                platform=platform,
                category=category,
                developer=developer,
                license=license_,
                architecture=architecture,
                open_source=open_source,
                min_trust=str(min_trust) if min_trust is not None else None,
                min_quality=str(min_quality) if min_quality is not None else None,
                updated_since=updated_since,
                sort=sort,
            )
            backend = "database"

        SEARCH_DURATION.observe(time.perf_counter() - started)
        SEARCH_RESULTS.observe(len(result.items))
        return result, backend

    def _meili_search(
        self,
        q: str,
        *,
        platform: str | None,
        category: str | None,
        developer: str | None,
        license_: str | None,
        open_source: str | None,
        sort: str | None,
        page: int,
        per_page: int,
    ) -> PaginatedApps:
        filters = _meili_filters(platform, category, developer, license_, open_source)
        raw = self.indexer.search(
            q,
            filters=filters,
            limit=per_page,
            offset=(page - 1) * per_page,
            sort=_meili_sort(sort),
        )
        hits = raw.get("hits") or []
        items: list[OmniStoreApp] = []
        for hit in hits:
            try:
                items.append(OmniStoreApp.model_validate(hit))
            except Exception:
                logger.warning("Dropping invalid Meilisearch hit: %s", hit.get("id"))
        return PaginatedApps(
            items=items,
            total=int(raw.get("estimatedTotalHits") or 0),
            page=page,
            freshness=None,
        )

    async def suggestions(self, q: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search suggestions from the index (empty when unavailable)."""
        if not q or not q.strip() or isinstance(self.indexer, NullSearchIndexer):
            return []
        try:
            return self.indexer.suggest(q, limit=limit)
        except Exception as exc:
            logger.warning("Suggest request failed: %s", exc)
            return []


__all__ = ["SearchService"]
