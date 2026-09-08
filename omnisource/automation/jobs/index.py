"""Search indexing job."""

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.core.repositories.application import ApplicationRepository
from omnisource.search.indexer import get_indexer

logger = get_logger(__name__)


async def run_indexing(
    session: AsyncSession,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Index all applications into the search engine."""
    repo = ApplicationRepository(session)
    apps = await repo.get_all_apps()

    documents = [app.model_dump(mode="json") for app in apps]

    indexer = get_indexer()
    indexer.index_apps(documents)

    logger.info("Indexing job completed: %d apps indexed", len(documents))
    return {"indexed": len(documents)}
