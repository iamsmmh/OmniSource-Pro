"""Meilisearch indexer with graceful fallback.

Index configuration (applied idempotently on startup and reindex):

* searchable: name, developer, bundle_id, description, tags, category
* filterable: platforms, categories, tags, license, open_source,
  developer, source_name
* sortable: popularity, trust, updated_at, name
* ranking rules: words -> typo -> proximity -> attribute -> sort -> exactness
* typo tolerance: min 5-char words, up to 2 typos on long words
* synonyms: curated equivalence groups (see :data:`DEFAULT_SYNONYMS`)
* suggestions: Meilisearch suggest endpoint with a ranked-search fallback
"""

from __future__ import annotations

from typing import Any

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings

logger = get_logger(__name__)

DEFAULT_SYNONYMS: dict[str, list[str]] = {
    "app": ["app", "application", "software"],
    "free": ["open source"],
    "oss": ["open source"],
    "editor": ["ide", "code editor"],
    "ide": ["editor", "code editor"],
    "chat": ["messenger", "im"],
    "messenger": ["chat", "im"],
    "browser": ["web browser"],
    "player": ["media player"],
    "media player": ["player"],
    "terminal": ["shell", "console"],
    "shell": ["terminal", "console"],
    "note": ["notebook", "notes"],
    "notes": ["notebook", "note"],
    "todo": ["task", "task manager"],
    "tasks": ["task", "todo"],
    "backup": ["backup tool", "sync"],
    "vpn": ["virtual private network", "tunnel"],
    "wifi": ["wi-fi"],
}

_RANKING_RULES = [
    "words",
    "typo",
    "proximity",
    "attribute",
    "sort",
    "exactness",
]

_TYPOTOLERANCE = {
    "enabled": True,
    "minWordSizeForTypos": {"oneTypo": 5, "twoTypos": 9},
    "disableOnWords": [],
    "disableOnAttributes": ["bundle_id"],
}


def build_index_settings() -> dict[str, Any]:
    """The full settings payload applied to the apps index."""
    return {
        "searchableAttributes": [
            "name",
            "developer",
            "bundle_id",
            "short_description",
            "description",
            "tags",
            "categories",
            "slug",
            "app_id",
        ],
        "filterableAttributes": [
            "platforms",
            "categories",
            "tags",
            "license",
            "open_source",
            "developer",
            "source_name",
            "bundle_id",
        ],
        "sortableAttributes": [
            "scores.popularity",
            "scores.trust",
            "download_count",
            "updated_at",
            "name",
        ],
        "rankingRules": _RANKING_RULES,
        "typoTolerance": _TYPOTOLERANCE,
        "synonyms": DEFAULT_SYNONYMS,
        "distinctAttribute": "app_id",
        "displayedAttributes": [
            "id",
            "app_id",
            "name",
            "slug",
            "developer",
            "bundle_id",
            "short_description",
            "description",
            "tags",
            "categories",
            "platforms",
            "license",
            "homepage",
            "scores",
            "download_count",
            "updated_at",
        ],
    }


class SearchIndexer:
    """Indexes applications in Meilisearch for full-text and faceted search."""

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        index_name: str | None = None,
    ):
        settings = get_settings()
        self.url = url or settings.meilisearch.MEILISEARCH_URL
        self.api_key = api_key or settings.meilisearch.MEILISEARCH_MASTER_KEY
        self.index_name = index_name or settings.meilisearch.MEILISEARCH_INDEX_NAME
        self._client: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            import meilisearch  # imported lazily so the package works without it

            self._client = meilisearch.Client(self.url, self.api_key)
        return self._client

    @property
    def index(self):
        return self.client.index(self.index_name)

    def configure_settings(self) -> None:
        """Apply the full index settings (idempotent)."""
        self.index.update_settings(build_index_settings())

    def get_settings(self) -> dict[str, Any]:
        """Fetch the live settings (used by the admin/verification API)."""
        return self.index.get_settings()

    def index_apps(self, apps: list[dict[str, Any]]) -> None:
        """Index a list of serialized applications."""
        if not apps:
            return
        self.index.add_documents(apps, primary_key="id")

    def delete_app(self, app_id: str) -> None:
        """Remove a single application from the index."""
        self.index.delete_document(app_id)

    def clear(self) -> None:
        """Delete all documents from the index."""
        self.index.delete_all_documents()

    def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 30,
        offset: int = 0,
        sort: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search the index and return Meilisearch results."""
        from omnisource.search.query import build_filter_string

        options: dict[str, Any] = {"limit": limit, "offset": offset}
        filter_str = build_filter_string(filters or {})
        if filter_str:
            options["filter"] = filter_str
        if sort:
            options["sort"] = sort
        return self.index.search(query, options)

    def suggest(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Query suggestions: distinct leading-phrase matches.

        Uses the Meilisearch suggest endpoint when the server supports it
        (v1.3+), falling back to a regular ranked search otherwise.
        """
        if not query or not query.strip():
            return []
        try:
            result = self.client.http_request(
                "POST",
                f"/indexes/{self.index_name}/suggest",
                body={"q": query, "limit": limit},
            )
            hits = result.get("hits") or []
        except Exception:
            try:
                result = self.index.search(query, {"limit": limit * 3})
                hits = result.get("hits") or []
            except Exception:
                return []
        suggestions: list[dict[str, Any]] = []
        seen: set[str] = set()
        for hit in hits:
            name = (hit.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            suggestions.append(
                {
                    "text": name,
                    "app_id": hit.get("app_id"),
                    "slug": hit.get("slug"),
                }
            )
            if len(suggestions) >= limit:
                break
        return suggestions


class NullSearchIndexer(SearchIndexer):
    """No-op indexer used when Meilisearch is unavailable or disabled."""

    @property
    def client(self):
        raise RuntimeError("Meilisearch is not available")

    def configure_settings(self) -> None:
        logger.debug("NullSearchIndexer: skipping settings configuration")

    def get_settings(self) -> dict[str, Any]:
        return {}

    def index_apps(self, apps: list[dict[str, Any]]) -> None:
        logger.debug("NullSearchIndexer: skipping indexing of %d apps", len(apps))

    def delete_app(self, app_id: str) -> None:
        logger.debug("NullSearchIndexer: skipping deletion of %s", app_id)

    def clear(self) -> None:
        logger.debug("NullSearchIndexer: skipping clear")

    def search(
        self, query: str, filters=None, limit: int = 30, offset: int = 0, sort=None
    ) -> dict[str, Any]:
        return {
            "hits": [],
            "query": query,
            "limit": limit,
            "offset": offset,
            "estimatedTotalHits": 0,
        }

    def suggest(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        return []


def get_indexer() -> SearchIndexer:
    """Return a search indexer, falling back to a no-op when unavailable."""
    settings = get_settings()
    if not settings.meilisearch.MEILISEARCH_URL:
        return NullSearchIndexer()
    try:
        import meilisearch  # noqa: F401 - optional dependency
    except ImportError:
        logger.warning("Meilisearch client is not installed; search indexing is disabled")
        return NullSearchIndexer()
    return SearchIndexer()


__all__ = [
    "DEFAULT_SYNONYMS",
    "NullSearchIndexer",
    "SearchIndexer",
    "build_index_settings",
    "get_indexer",
]
