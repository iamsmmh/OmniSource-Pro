"""Outbound webhook subscriptions for event push notifications."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from omnisource.core.models.base import Base

if TYPE_CHECKING:
    pass


class NotificationEvent(str, Enum):
    """Events consumers can subscribe to."""

    RELEASE_CREATED = "release.created"
    APP_UPDATED = "app.updated"
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
    failure_count: Mapped[int] = mapped_column(default=0)
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


__all__ = ["NotificationEvent", "WebhookSubscription"]
