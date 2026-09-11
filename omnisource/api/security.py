"""API authentication for OmniSource.

Provides API-key authentication for administrative and write endpoints.
Keys are configured through settings (``API_API_KEYS``, comma-separated)
and compared in constant time. Read endpoints stay open by default so
OmniStore clients work out of the box; set ``API_AUTH_REQUIRED=true`` to
require a key on every route.

Usage in a route::

    @router.post("", dependencies=[Depends(require_api_key)])
    async def create_something(...): ...
"""

import hashlib
import hmac
import secrets
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings

logger = get_logger(__name__)

_API_KEY_HEADER = "X-API-Key"
_api_key_header = APIKeyHeader(name=_API_KEY_HEADER, auto_error=False)


class APIKeyAuth:
    """Validates requests against the configured API keys."""

    def __init__(self, keys: list[str] | None = None) -> None:
        settings = get_settings()
        configured = keys if keys is not None else settings.api.API_KEYS
        self._keys = {key.strip() for key in configured if key.strip()}

    @property
    def enabled(self) -> bool:
        """Auth is enforced only when at least one key is configured."""
        return bool(self._keys)

    def verify(self, provided: str | None) -> bool:
        if not provided:
            return False
        for key in self._keys:
            if secrets.compare_digest(provided, key):
                return True
        return False


async def require_api_key(request: Request, api_key: str | None = Depends(_api_key_header)) -> str:
    """FastAPI dependency that rejects requests without a valid API key."""
    auth = _auth_for_request(request)
    if not auth.verify(api_key):
        logger.warning("Rejected request to %s: missing or invalid API key", request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key or ""


async def require_omnistore_subject(
    subject: str | None = Header(default=None, alias="X-OmniStore-Subject"),
    _api_key: str = Depends(require_api_key),
) -> str:
    """Return a non-reversible subject key for authenticated personal data APIs.

    Favorites, private collections, and personalized analytics are service-to-
    service integration endpoints.  OmniStore must authenticate with an API
    key and pass the stable upstream account subject in this header.  The raw
    value is deliberately neither persisted nor returned by OmniSource.
    """
    if not subject or not subject.strip() or len(subject) > 256:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid subject"
        )
    secret = get_settings().security.SECRET_KEY.encode("utf-8")
    return hmac.new(secret, subject.strip().encode("utf-8"), hashlib.sha256).hexdigest()


def _auth_for_request(request: Request) -> APIKeyAuth:
    """Reuse the per-app auth instance created at startup when available."""
    auth: Any | None = getattr(request.app.state, "api_key_auth", None)
    return auth if isinstance(auth, APIKeyAuth) else APIKeyAuth()


def configure_app_auth(app: Any) -> APIKeyAuth:
    """Create the shared auth instance and attach it to the app state."""
    auth = APIKeyAuth()
    app.state.api_key_auth = auth
    return auth


__all__ = [
    "APIKeyAuth",
    "configure_app_auth",
    "require_api_key",
    "require_omnistore_subject",
]
