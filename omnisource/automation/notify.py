"""Outbound notification dispatcher.

Delivers signed event payloads to webhook subscriptions. Delivery is
fire-and-forget from the caller's perspective: failures increment a failure
counter (auto-disabling after ``max_failures``) and never raise into the
pipeline.

Payloads are signed with each subscription's own secret:
``X-OmniSource-Signature: sha256=<hmac_sha256(secret, body)>``
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.core.models.notification import NotificationEvent, WebhookSubscription

logger = get_logger(__name__)

_DELIVERY_TIMEOUT = 10.0
_MAX_FAILURES = 20
_USER_AGENT = "OmniSource-Notifications/0.1.0"


def sign_payload(secret: str, body: bytes) -> str:
    """HMAC-sign a delivery body the same way deliveries are verified."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def build_payload(event: str, data: dict[str, Any]) -> bytes:
    """Build the JSON body for a notification."""
    envelope = {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        "data": data,
    }
    return json.dumps(envelope, separators=(",", ":"), default=str).encode()


async def dispatch_event(
    session: AsyncSession,
    event: str,
    data: dict[str, Any],
) -> int:
    """Notify all active subscribers of an event. Returns deliveries attempted."""
    result = await session.execute(
        select(WebhookSubscription).where(WebhookSubscription.is_active.is_(True))
    )
    subscriptions = [s for s in result.scalars().all() if s.delivers(event)]
    if not subscriptions:
        return 0

    body = build_payload(event, data)
    attempted = 0
    async with httpx.AsyncClient(
        timeout=_DELIVERY_TIMEOUT, headers={"User-Agent": _USER_AGENT}
    ) as client:
        for subscription in subscriptions:
            attempted += 1
            await _deliver(client, subscription, body)
    await session.commit()
    return attempted


async def _deliver(
    client: httpx.AsyncClient, subscription: WebhookSubscription, body: bytes
) -> None:
    """Attempt one delivery and record the outcome on the subscription."""
    headers = {
        "Content-Type": "application/json",
        "X-OmniSource-Event": json.loads(body).get("event", ""),
        "X-OmniSource-Signature": sign_payload(subscription.secret, body),
    }
    status: str
    try:
        response = await client.post(subscription.url, content=body, headers=headers)
        status = str(response.status_code)
    except httpx.HTTPError as exc:
        logger.warning("Notification delivery to %s failed: %s", subscription.url, exc)
        status = "error"

    subscription.last_delivery_at = datetime.now(UTC)
    subscription.last_delivery_status = status
    if status.startswith("2"):
        subscription.failure_count = 0
        subscription.last_success_at = datetime.now(UTC)
    else:
        subscription.failure_count = (subscription.failure_count or 0) + 1
        if subscription.failure_count >= _MAX_FAILURES:
            logger.warning(
                "Disabling subscription %s after %d consecutive failures",
                subscription.url,
                subscription.failure_count,
            )
            subscription.is_active = False


def ensure_notification_events_valid(events: list[str]) -> list[str]:
    """Validate event names against the known enum (allows '*')."""
    valid = {e.value for e in NotificationEvent} | {"*"}
    return [e for e in events if e in valid]


__all__ = [
    "build_payload",
    "dispatch_event",
    "ensure_notification_events_valid",
    "sign_payload",
]
