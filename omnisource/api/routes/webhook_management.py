"""Outbound webhook endpoint management API (API-key protected).

OmniStore-Pro (and future Omni clients) register a consumer endpoint and
subscribe to the ecosystem events:

    app_created, app_updated, app_deleted, feed_synced
    (+ legacy: release.created, app.updated, quarantine.created, feed.updated)

Deliveries are HMAC-signed (``X-OmniSource-Signature: sha256=...``), retried
with exponential backoff, and auditable via ``GET /deliveries``.
"""

import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from omnisource.api.dependencies import get_db
from omnisource.api.envelope import success
from omnisource.api.security import require_api_key
from omnisource.core.models.webhook import (
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookSubscription,
)
from omnisource.webhooks.delivery import build_payload, sign_payload, valid_event_names

router = APIRouter()

_EVENT_ALIASES = {
    "app.created": "app_created",
    "app.deleted": "app_deleted",
    "feed.synced": "feed_synced",
}


def _normalize_events(raw: list[Any] | None) -> list[str]:
    valid = set(valid_event_names()) | {"*"}
    events: list[str] = []
    for item in raw or ["*"]:
        event = str(item).strip()
        event = _EVENT_ALIASES.get(event, event)
        if event in valid and event not in events:
            events.append(event)
    if not events:
        raise HTTPException(status_code=422, detail="no valid events provided")
    return events


@router.get("/endpoints")
async def list_endpoints(session=Depends(get_db), _key: str = Depends(require_api_key)):
    """List registered webhook endpoints (secrets are never returned)."""
    rows = (
        (
            await session.execute(
                select(WebhookSubscription).order_by(WebhookSubscription.created_at)
            )
        )
        .scalars()
        .all()
    )
    return success(
        data={
            "items": [
                {
                    "id": str(row.id),
                    "url": row.url,
                    "events": row.events,
                    "description": row.description,
                    "is_active": row.is_active,
                    "failure_count": row.failure_count,
                    "last_delivery_status": row.last_delivery_status,
                    "last_delivery_at": row.last_delivery_at.isoformat()
                    if row.last_delivery_at
                    else None,
                    "last_success_at": row.last_success_at.isoformat()
                    if row.last_success_at
                    else None,
                }
                for row in rows
            ]
        }
    )


@router.post("/endpoints", status_code=status.HTTP_201_CREATED)
async def create_endpoint(
    payload: dict[str, Any],
    session=Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """Register a webhook endpoint. The HMAC secret is returned exactly once."""
    url = str(payload.get("url") or "").strip()
    if not url.startswith(("http://", "https://")) or len(url) > 1000:
        raise HTTPException(status_code=422, detail="url must be an http(s) URL")
    events = _normalize_events(payload.get("events"))

    existing = (
        await session.execute(select(WebhookSubscription).where(WebhookSubscription.url == url))
    ).scalar_one_or_none()
    if existing is not None and existing.is_active:
        raise HTTPException(status_code=409, detail="endpoint already registered")

    secret = secrets.token_urlsafe(32)
    subscription = WebhookSubscription(
        url=url,
        events=events,
        secret=secret,
        description=str(payload.get("description") or "")[:500] or None,
        is_active=True,
    )
    session.add(subscription)
    await session.commit()
    return success(
        data={
            "id": str(subscription.id),
            "url": subscription.url,
            "events": subscription.events,
            "secret": secret,
        },
        meta={"note": "store the secret now; it is not retrievable later"},
    )


@router.patch("/endpoints/{endpoint_id}")
async def update_endpoint(
    endpoint_id: str,
    payload: dict[str, Any],
    session=Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """Update an endpoint's event subscriptions, description, or active state."""
    subscription = await session.get(WebhookSubscription, endpoint_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="endpoint not found")
    if "events" in payload:
        subscription.events = _normalize_events(payload.get("events"))
    if payload.get("description") is not None:
        subscription.description = str(payload["description"])[:500] or None
    if "is_active" in payload:
        subscription.is_active = bool(payload["is_active"])
    await session.commit()
    return success(
        data={
            "id": str(subscription.id),
            "url": subscription.url,
            "events": subscription.events,
            "is_active": subscription.is_active,
        }
    )


@router.delete("/endpoints/{endpoint_id}")
async def delete_endpoint(
    endpoint_id: str,
    session=Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """Deactivate an endpoint (soft delete; pending deliveries go dead)."""
    subscription = await session.get(WebhookSubscription, endpoint_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="endpoint not found")
    subscription.is_active = False
    await session.commit()
    return success(data={"id": str(subscription.id), "status": "deactivated"})


@router.post("/endpoints/{endpoint_id}/test")
async def test_endpoint(
    endpoint_id: str,
    session=Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """Send a signed test delivery directly to one endpoint and report the HTTP status."""
    import httpx

    subscription = await session.get(WebhookSubscription, endpoint_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="endpoint not found")
    body = build_payload(
        "feed_synced",
        {
            "test": True,
            "note": "test delivery from the OmniSource webhook management API",
            "endpoint": str(subscription.id),
        },
    )
    headers = {
        "Content-Type": "application/json",
        "X-OmniSource-Event": "feed_synced",
        "X-OmniSource-Signature": sign_payload(subscription.secret, body),
        "User-Agent": "OmniSource-Webhooks/1.0",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(subscription.url, content=body, headers=headers)
        subscription.last_delivery_at = datetime.now(UTC)
        subscription.last_delivery_status = str(response.status_code)
        if 200 <= response.status_code < 300:
            subscription.last_success_at = datetime.now(UTC)
            subscription.failure_count = 0
        await session.commit()
        http_status = response.status_code
    except httpx.HTTPError as exc:
        subscription.last_delivery_status = "error"
        await session.commit()
        return success(
            data={"endpoint": str(subscription.id), "delivered": False, "error": str(exc)[:300]},
            meta={"verify": "the endpoint is unreachable from this host"},
        )
    return success(
        data={
            "endpoint": str(subscription.id),
            "delivered": 200 <= http_status < 300,
            "http_status": http_status,
        },
        meta={"verify": "check X-OmniSource-Event and X-OmniSource-Signature on your receiver"},
    )


@router.get("/deliveries")
async def list_deliveries(
    event: str | None = Query(default=None, max_length=64),
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    limit: int = Query(default=50, ge=1, le=500),
    session=Depends(get_db),
    _key: str = Depends(require_api_key),
):
    """Recent outbound webhook deliveries (audit view)."""
    query = select(WebhookDelivery)
    if event:
        query = query.where(WebhookDelivery.event == event)
    if status_filter:
        try:
            query = query.where(WebhookDelivery.status == WebhookDeliveryStatus(status_filter))
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid status") from None
    rows = (
        (await session.execute(query.order_by(WebhookDelivery.created_at.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return success(
        data={
            "items": [
                {
                    "id": str(row.id),
                    "endpoint_id": str(row.endpoint_id),
                    "event": row.event,
                    "status": row.status.value,
                    "attempts": row.attempts,
                    "max_attempts": row.max_attempts,
                    "last_error": row.last_error,
                    "response_status": row.response_status,
                    "next_attempt_at": row.next_attempt_at.isoformat()
                    if row.next_attempt_at
                    else None,
                    "sent_at": row.sent_at.isoformat() if row.sent_at else None,
                }
                for row in rows
            ]
        }
    )
