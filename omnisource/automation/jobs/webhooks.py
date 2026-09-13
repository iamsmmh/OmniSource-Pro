"""Webhook delivery job: processes the outbound delivery queue."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.webhooks.delivery import deliver_pending

logger = get_logger(__name__)


async def run_webhook_delivery(
    session: AsyncSession, limit: int = 100, **kwargs: Any
) -> dict[str, Any]:
    """Deliver all due webhook deliveries (retry queue)."""
    result = await deliver_pending(session, limit=limit)
    if result.get("processed"):
        logger.info("Webhook delivery batch: %s", result)
    return result


__all__ = ["run_webhook_delivery"]
