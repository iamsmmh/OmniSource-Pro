"""GitHub data provider for the feed sync engine.

Wraps the shared :class:`~omnisource.connectors.github.client.GitHubClient`
(which already implements retry, caching, and token-bucket rate limiting) and
adds the feed pipeline's needs:

* **Incremental sync** - conditional requests with ``If-None-Match`` ETags;
  an unchanged repository costs no body processing and a 304 never counts
  against the hourly quota.
* **Rate-limit handling** - exposes remaining quota and reset time so the
  engine can pause instead of hammering a 429, and converts client rate-limit
  errors into a typed :class:`ProviderRateLimited` the engine retries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings

logger = get_logger(__name__)


class ProviderError(Exception):
    """Base error for provider failures (retriable by default)."""


class ProviderRateLimited(ProviderError):
    """The upstream rate limit was exhausted; wait for the reset."""

    def __init__(self, reset_at: datetime | None = None) -> None:
        super().__init__("GitHub API rate limit exceeded")
        self.reset_at = reset_at


class ProviderAuthError(ProviderError):
    """Authentication failed; retrying immediately will not help."""


class ProviderNotFoundError(ProviderError):
    """The repository does not exist (404)."""


class GitHubFeedProvider:
    """Fetches repository and release payloads from GitHub."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def _ensure_client(self) -> Any:
        if self._client is None:
            from omnisource.connectors.github.client import GitHubClient

            settings = get_settings()
            self._client = GitHubClient(
                token=settings.github.GH_TOKEN,
                timeout=settings.github.GH_REQUEST_TIMEOUT,
                retry_count=settings.github.GH_RETRY_COUNT,
            )
        await self._client.initialize()
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            try:
                await self._client.close()
            except Exception:  # pragma: no cover - best effort
                logger.debug("Error closing GitHub client", exc_info=True)
            self._client = None

    async def __aenter__(self) -> GitHubFeedProvider:
        await self._ensure_client()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Rate limit visibility
    # ------------------------------------------------------------------

    def rate_limit_remaining(self) -> int | None:
        try:
            client = self._client
            if client is None:
                return None
            return client.rate_limiter.requests_remaining()
        except Exception:
            return None

    def seconds_until_rate_reset(self) -> float | None:
        try:
            client = self._client
            if client is None:
                return None
            return client.rate_limiter.time_until_reset()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Fetches
    # ------------------------------------------------------------------

    async def fetch_repository(
        self, full_name: str, etag: str | None = None
    ) -> tuple[Any, str | None]:
        """Fetch a repository payload.

        Returns ``(payload, etag)``. ``payload`` is ``None`` when the ETag was
        unchanged (304 Not Modified) - in that case ``etag`` is the
        previously supplied ETag, which stays valid as the checkpoint.
        """
        client = await self._ensure_client()
        try:
            response = await client.get(f"/repos/{full_name}", etag=etag, use_cache=False)
        except Exception as exc:  # map client error taxonomy to provider errors
            raise self._translate(exc) from exc
        if response.status_code == 304:
            return None, etag
        response.raise_for_status()
        payload: Any = response.json()
        new_etag = response.headers.get("ETag")
        return payload, new_etag

    async def fetch_releases(self, full_name: str, limit: int = 15) -> list[Any]:
        """Fetch the most recent releases (newest first)."""
        client = await self._ensure_client()
        try:
            response = await client.get(
                f"/repos/{full_name}/releases",
                params={"per_page": min(limit, 100)},
                use_cache=False,
            )
        except Exception as exc:
            raise self._translate(exc) from exc
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    @staticmethod
    def _translate(exc: Exception) -> ProviderError:
        message = str(exc).lower()
        error_class = type(exc).__name__
        if "ratelimiterror" in error_class or "rate limit" in message:
            return ProviderRateLimited()
        if "autherror" in error_class or "authentication" in message or "401" in message:
            return ProviderAuthError(message)
        if "http_404" in message or "not found" in message or "404" in message:
            return ProviderNotFoundError(message)
        return ProviderError(message)


__all__ = [
    "GitHubFeedProvider",
    "ProviderAuthError",
    "ProviderError",
    "ProviderNotFoundError",
    "ProviderRateLimited",
]
