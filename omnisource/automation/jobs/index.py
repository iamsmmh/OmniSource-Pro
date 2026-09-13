"""Search indexing job (automatic reindex workflow).

A full reindex rebuilds the Meilisearch index from PostgreSQL: settings are
re-applied (synonyms, typo tolerance, ranking rules), stale documents are
replaced, and the run is logged for the observability stack. Incremental
indexing happens automatically in the feed publisher after every sync.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.core.repositories.application import ApplicationRepository
from omnisource.search.indexer import NullSearchIndexer, get_indexer

logger = get_logger(__name__)


async def run_indexing(
    session: AsyncSession,
    **kwargs: Any,
) -> dict[str, Any]:
    """Reindex all applications into the search engine."""
    indexer = get_indexer()
    repo = ApplicationRepository(session)
    apps = await repo.get_all_apps()
    documents = [app.model_dump(mode="json") for app in apps]

    if isinstance(indexer, NullSearchIndexer):
        logger.info(
            "Search indexing skipped (%d apps counted): Meilisearch not configured", len(documents)
        )
        return {"indexed": len(documents), "skipped": True}

    indexer.configure_settings()
    if documents:
        indexer.index_apps(documents)

    logger.info("Indexing job completed: %d apps indexed", len(documents))
    return {"indexed": len(documents), "skipped": False}


__all__ = ["run_indexing"]
