"""Meilisearch indexer with graceful fallback."""

from typing import Any, Dict, List, Optional

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings

logger = get_logger(__name__)


class SearchIndexer:
    """Indexes applications in Meilisearch for full-text and faceted search."""

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        index_name: Optional[str] = None,
    ):
        settings = get_settings()
        self.url = url or settings.meilisearch.MEILISEARCH_URL
        self.api_key = api_key or settings.meilisearch.MEILISEARCH_MASTER_KEY
        self.index_name = index_name or settings.meilisearch.MEILISEARCH_INDEX_NAME
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import meilisearch  # imported lazily so the package works without it

            self._client = meilisearch.Client(self.url, self.api_key)
        return self._client

    @property
    def index(self):
        return self.client.index(self.index_name)

    def configure_settings(self) -> None:
        """Configure searchable/filterable/sortable attributes."""
        self.index.update_settings(
            {
                "searchableAttributes": ["name", "short_description", "description", "slug", "app_id"],
                "filterableAttributes": [
                    "platforms",
                    "categories",
                    "tags",
                    "license",
                    "open_source",
                    "source_name",
                ],
                "sortableAttributes": ["scores.popularity", "scores.trust", "updated_at", "name"],
                "rankingRules": [
                    "words",
                    "typo",
                    "proximity",
                    "attribute",
                    "sort",
                    "exactness",
                ],
            }
        )

    def index_apps(self, apps: List[Dict[str, Any]]) -> None:
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
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 30,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Search the index and return Meilisearch results."""
        from omnisource.search.query import build_filter_string

        options: Dict[str, Any] = {"limit": limit, "offset": offset}
        filter_str = build_filter_string(filters or {})
        if filter_str:
            options["filter"] = filter_str
        return self.index.search(query, options)


class NullSearchIndexer(SearchIndexer):
    """No-op indexer used when Meilisearch is unavailable or disabled."""

    @property
    def client(self):
        raise RuntimeError("Meilisearch is not available")

    def configure_settings(self) -> None:
        logger.debug("NullSearchIndexer: skipping settings configuration")

    def index_apps(self, apps: List[Dict[str, Any]]) -> None:
        logger.debug("NullSearchIndexer: skipping indexing of %d apps", len(apps))

    def delete_app(self, app_id: str) -> None:
        logger.debug("NullSearchIndexer: skipping deletion of %s", app_id)

    def clear(self) -> None:
        logger.debug("NullSearchIndexer: skipping clear")

    def search(self, query: str, filters=None, limit=30, offset=0) -> Dict[str, Any]:
        return {"hits": [], "query": query, "limit": limit, "offset": offset, "estimatedTotalHits": 0}


def get_indexer() -> SearchIndexer:
    """Return a search indexer, falling back to a no-op when unavailable."""
    settings = get_settings()
    if not settings.meilisearch.MEILISEARCH_URL:
        return NullSearchIndexer()
    try:
        import meilisearch  # noqa: F401 - optional dependency
    except ImportError:
        logger.warning(
            "Meilisearch client is not installed; search indexing is disabled"
        )
        return NullSearchIndexer()
    return SearchIndexer()
