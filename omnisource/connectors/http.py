"""Shared resilient HTTP primitives for non-GitHub source connectors."""

import asyncio
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from omnisource.connectors.base import ConnectorError
from omnisource.connectors.rate_limiter import RateLimiter

_RETRIABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), 60.0))
            except ValueError:
                try:
                    return max(
                        0.0,
                        min(
                            (
                                parsedate_to_datetime(retry_after) - datetime.now(UTC)
                            ).total_seconds(),
                            60.0,
                        ),
                    )
                except (TypeError, ValueError):
                    pass
    return min(2**attempt, 30.0)


def _update_rate_state(response: httpx.Response, limiter: RateLimiter | None) -> None:
    if limiter is None:
        return
    remaining = response.headers.get(
        "X-RateLimit-Remaining", response.headers.get("RateLimit-Remaining")
    )
    reset = response.headers.get("X-RateLimit-Reset")
    if remaining is not None:
        try:
            limiter.update_remaining(max(0, int(remaining)))
        except ValueError:
            pass
    if reset is not None:
        try:
            limiter.update_reset(datetime.fromtimestamp(int(reset), UTC))
        except ValueError:
            pass


async def get_with_retry(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    limiter: RateLimiter | None = None,
    attempts: int = 3,
) -> httpx.Response:
    """GET with token-bucket enforcement, Retry-After, and exponential recovery.

    The final response is returned so the connector can translate source-
    specific status codes into its public ``ConnectorError`` contract.
    """
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        if limiter is not None:
            await limiter.wait_for_token()
        try:
            response = await client.get(path, params=params)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt < attempts - 1:
                await asyncio.sleep(_retry_delay(None, attempt))
                continue
            raise ConnectorError(f"Network error requesting {path}: {exc}") from exc
        _update_rate_state(response, limiter)
        if response.status_code not in _RETRIABLE_STATUS_CODES or attempt == attempts - 1:
            return response
        await asyncio.sleep(_retry_delay(response, attempt))
    raise ConnectorError(f"Network error requesting {path}: {last_error}")


__all__ = ["get_with_retry"]
