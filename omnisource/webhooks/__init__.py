"""Outbound webhooks for Omni ecosystem clients.

OmniStore-Pro (and future Omni clients) register an endpoint and receive
HMAC-signed POST deliveries for:

* ``app_created``   - a new application entered the catalogue
* ``app_updated``   - an existing application changed
* ``app_deleted``   - an application was removed/deactivated
* ``feed_synced``   - a feed sync run completed (payload includes stats)

Delivery is reliable: every event x endpoint becomes a ``WebhookDelivery``
row; failures retry with exponential backoff (15s, 30s, ... capped at 5min,
8 attempts) and are auditable through the admin API.
"""

from omnisource.webhooks.delivery import (
    MAX_ATTEMPTS,
    deliver_pending,
    emit_event,
)

__all__ = ["MAX_ATTEMPTS", "deliver_pending", "emit_event"]
