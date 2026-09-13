"""Compatibility module.

The webhook models now live in :mod:`omnisource.core.models.webhook` (with the
delivery audit table). This module re-exports them so existing imports keep
working.
"""

from omnisource.core.models.webhook import (
    NotificationEvent,
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookSubscription,
)

__all__ = [
    "NotificationEvent",
    "WebhookDelivery",
    "WebhookDeliveryStatus",
    "WebhookSubscription",
]
