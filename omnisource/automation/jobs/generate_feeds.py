"""Feed generation job."""

from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.feeds.generator import FeedGenerator

logger = get_logger(__name__)


async def run_feed_generation(
    session: AsyncSession,
    platform: str = "all",
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """Generate platform feeds."""
    generator = FeedGenerator(session)
    if platform == "all":
        results = await generator.generate_all()
    else:
        results = [await generator.generate(platform)]

    logger.info("Feed generation job completed: %d feeds", len(results))
    return results
