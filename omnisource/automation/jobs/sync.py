"""Repository synchronization job."""

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.crawler.sync import RepositorySyncService

logger = get_logger(__name__)


async def run_sync(
    session: AsyncSession,
    source_type: str = "github",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Run a synchronization pass for a source type."""
    service = RepositorySyncService(session)
    result = await service.sync_source(source_type=source_type)
    logger.info("Sync job completed: %s", result)
    return result
