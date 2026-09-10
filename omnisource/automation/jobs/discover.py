"""Repository discovery job."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.crawler.discovery import DiscoveryService

logger = get_logger(__name__)


async def run_discovery(
    session: AsyncSession,
    source_type: str = "github",
    **kwargs: Any,
) -> dict[str, Any]:
    """Run a discovery pass for a source type."""
    service = DiscoveryService(session)
    result = await service.discover(source_type=source_type, **kwargs)
    logger.info("Discovery job completed: %s", result)
    return result
