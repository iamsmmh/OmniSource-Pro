"""Outbound webhook subscription and delivery models.

``WebhookSubscription`` is a registered consumer endpoint; ``WebhookDelivery``
is the per-event, per-endpoint audit row that drives retry-with-backoff
delivery and exposes delivery status to the admin API.
"""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from omnisource.core.models.base import Base


class NotificationEvent(str, Enum):
    """Events consumers can subscribe to.

    The ``app_*`` / ``feed_synced`` values are the Omni ecosystem contract:
    OmniStore-Pro refreshes automatically when it receives any of them. The
    legacy dotted names are kept for existing subscribers.
    """

    APP_CREATED = "app_created"
    APP_UPDATED = "app_updated"
    APP_DELETED = "app_deleted"
    FEED_SYNCED = "feed_synced"
    RELEASE_CREATED = "release.created"
    APP_UPDATED_LEGACY = "app.updated"
    QUARANTINE_CREATED = "quarantine.created"
    FEED_UPDATED = "feed.updated"


class WebhookSubscription(Base):
    """A consumer URL that receives signed POST notifications on events."""

    __tablename__ = "webhook_subscriptions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    events: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_delivery_status: Mapped[str | None] = mapped_column(String(20))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def delivers(self, event: str) -> bool:
        """Whether this subscription receives the given event type."""
        if not self.is_active:
            return False
        if "*" in self.events:
            return True
        return event in self.events


class WebhookDeliveryStatus(str, Enum):
    """Lifecycle state of a single webhook delivery."""

    PENDING = "pending"
    SENT = "sent"
    RETRYING = "retrying"
    FAILED = "failed"
    DEAD = "dead"


class WebhookDelivery(Base):
    """One event-to-endpoint delivery with retry scheduling."""

    __tablename__ = "webhook_deliveries"
    __table_args__ = ({"comment": "Outbound webhook delivery audit and retry queue"},)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    endpoint_id: Mapped[UUID] = mapped_column(
        ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        SQLEnum(WebhookDeliveryStatus),
        default=WebhookDeliveryStatus.PENDING,
        nullable=False,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_error: Mapped[str | None] = mapped_column(String(500))
    response_status: Mapped[int | None] = mapped_column(Integer)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def is_due(self, now: datetime | None = None) -> bool:
        """Whether this delivery may be attempted right now."""
        if self.status not in (WebhookDeliveryStatus.PENDING, WebhookDeliveryStatus.RETRYING):
            return False
        now = now or datetime.now(UTC)
        if self.next_attempt_at is None:
            return True
        if self.next_attempt_at.tzinfo is None:
            self.next_attempt_at = self.next_attempt_at.replace(tzinfo=UTC)
        return self.next_attempt_at <= now


__all__ = [
    "NotificationEvent",
    "WebhookDelivery",
    "WebhookDeliveryStatus",
    "WebhookSubscription",
]
