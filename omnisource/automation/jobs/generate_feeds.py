"""Feed generation job."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.feeds.generator import FeedGenerator

logger = get_logger(__name__)


async def run_feed_generation(
    session: AsyncSession,
    platform: str = "all",
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Generate platform feeds."""
    generator = FeedGenerator(session)
    if platform == "all":
        results = await generator.generate_all()
    else:
        results = [await generator.generate(platform)]

    logger.info("Feed generation job completed: %d feeds", len(results))

    # Notify subscribers that feeds changed (best-effort, never raises).
    try:
        from omnisource.automation.notify import dispatch_event

        await dispatch_event(
            session,
            "feed.updated",
            {"platforms": [str(r.get("platform", r)) for r in results]},
        )
    except Exception as exc:
        logger.warning("Feed notification failed: %s", exc)

    return results
