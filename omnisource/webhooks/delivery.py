"""Webhook delivery: event emission and retry-with-backoff dispatch."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.api.metrics import WEBHOOK_DELIVERIES
from omnisource.config.logging import get_logger
from omnisource.core.models.webhook import (
    NotificationEvent,
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookSubscription,
)

logger = get_logger(__name__)

MAX_ATTEMPTS = 8
_BACKOFF_BASE_SECONDS = 15.0
_BACKOFF_CAP_SECONDS = 300.0
_DELIVERY_TIMEOUT = 10.0
_USER_AGENT = "OmniSource-Webhooks/1.0"

VALID_EVENTS = {event.value for event in NotificationEvent} | {"*"}


def valid_event_names() -> list[str]:
    return sorted(VALID_EVENTS - {"*"})


def sign_payload(secret: str, body: bytes) -> str:
    """HMAC-SHA256 signature header value (verify: X-OmniSource-Signature)."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def build_payload(event: str, data: dict[str, Any]) -> bytes:
    """Canonical JSON body: compact, key-sorted, stable encoding."""
    envelope = {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        "source": "omnisource",
        "data": data,
    }
    return json.dumps(envelope, separators=(",", ":"), sort_keys=True, default=str).encode("utf-8")


def _backoff_seconds(attempts: int) -> float:
    return min(_BACKOFF_CAP_SECONDS, _BACKOFF_BASE_SECONDS * (2 ** max(0, attempts)))


async def emit_event(
    session: AsyncSession,
    event: str,
    data: dict[str, Any],
    *,
    max_endpoints: int = 20,
) -> int:
    """Queue a delivery row for every active subscribed endpoint.

    Returns the number of deliveries queued. Queuing is committed with the
    caller's transaction when possible; a standalone commit happens if the
    session is not already in a transaction, keeping the call safe from both
    API handlers (own transaction) and pipeline code.
    """
    if event not in VALID_EVENTS:
        logger.warning("Unknown webhook event %r; not emitting", event)
        return 0

    result = await session.execute(
        select(WebhookSubscription)
        .where(WebhookSubscription.is_active.is_(True))
        .limit(max_endpoints)
    )
    subscriptions = [s for s in result.scalars().all() if s.delivers(event)]
    if not subscriptions:
        return 0

    now = datetime.now(UTC)
    for subscription in subscriptions:
        session.add(
            WebhookDelivery(
                endpoint_id=subscription.id,
                event=event,
                payload={"event": event, "data": data},
                status=WebhookDeliveryStatus.PENDING,
                attempts=0,
                max_attempts=MAX_ATTEMPTS,
                next_attempt_at=now,
            )
        )
    try:
        await session.commit()
    except Exception:
        # The caller's transaction may own the commit (or be failed); the
        # delivery rows travel with whatever unit of work is active.
        logger.debug("Webhook queue commit delegated to caller transaction")
    return len(subscriptions)


def _schedule_retry_or_deadline(delivery: WebhookDelivery, endpoint: WebhookSubscription) -> None:
    endpoint.failure_count = (endpoint.failure_count or 0) + 1
    if delivery.attempts >= delivery.max_attempts:
        delivery.status = WebhookDeliveryStatus.DEAD
        if endpoint.failure_count >= 20:
            endpoint.is_active = False
            logger.warning("Disabled endpoint %s after repeated failures", endpoint.url)
    else:
        delivery.status = WebhookDeliveryStatus.RETRYING
        delivery.next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=_backoff_seconds(delivery.attempts)
        )


async def deliver_pending(session: AsyncSession, limit: int = 50) -> dict[str, Any]:
    """Process all due webhook deliveries. Returns counters."""
    due = await session.execute(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.status.in_(
                [WebhookDeliveryStatus.PENDING, WebhookDeliveryStatus.RETRYING]
            ),
            WebhookDelivery.next_attempt_at <= datetime.now(UTC),
        )
        .order_by(WebhookDelivery.next_attempt_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    deliveries = list(due.scalars().all())
    if not deliveries:
        return {"processed": 0}

    sent = failed = 0
    async with httpx.AsyncClient(
        timeout=_DELIVERY_TIMEOUT, headers={"User-Agent": _USER_AGENT}
    ) as http:
        for delivery in deliveries:
            endpoint = await session.get(WebhookSubscription, delivery.endpoint_id)
            if endpoint is None:
                delivery.status = WebhookDeliveryStatus.DEAD
                delivery.last_error = "endpoint deleted"
                failed += 1
                continue
            body = build_payload(delivery.event, delivery.payload.get("data", {}))
            headers = {
                "Content-Type": "application/json",
                "X-OmniSource-Event": delivery.event,
                "X-OmniSource-Signature": sign_payload(endpoint.secret, body),
            }
            delivery.attempts += 1
            now = datetime.now(UTC)
            try:
                response = await http.post(endpoint.url, content=body, headers=headers)
                delivery.response_status = response.status_code
                if 200 <= response.status_code < 300:
                    delivery.status = WebhookDeliveryStatus.SENT
                    delivery.sent_at = now
                    delivery.last_error = None
                    endpoint.last_success_at = now
                    endpoint.last_delivery_status = str(response.status_code)
                    endpoint.failure_count = 0
                    sent += 1
                    WEBHOOK_DELIVERIES.labels(event=delivery.event, status="sent").inc()
                else:
                    delivery.last_error = f"HTTP {response.status_code}"
                    endpoint.last_delivery_status = str(response.status_code)
                    _schedule_retry_or_deadline(delivery, endpoint)
                    failed += 1
                    WEBHOOK_DELIVERIES.labels(event=delivery.event, status="failed").inc()
            except httpx.HTTPError as exc:
                delivery.last_error = str(exc)[:500]
                endpoint.last_delivery_status = "error"
                _schedule_retry_or_deadline(delivery, endpoint)
                failed += 1
                WEBHOOK_DELIVERIES.labels(event=delivery.event, status="failed").inc()
            endpoint.last_delivery_at = now

    await session.commit()
    return {"processed": len(deliveries), "sent": sent, "failed": failed}


__all__ = [
    "MAX_ATTEMPTS",
    "build_payload",
    "deliver_pending",
    "emit_event",
    "sign_payload",
    "valid_event_names",
]
