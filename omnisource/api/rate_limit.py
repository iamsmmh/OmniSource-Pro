"""Rate limiting middleware for OmniSource.

Implements a fixed-window limiter keyed by client IP (or API key). Backed by
Redis when available; falls back to an in-process sliding window so local
development and tests work without Redis.

The limit per minute comes from ``API_RATE_LIMIT`` and can be raised per
identity with ``API_RATE_LIMIT_WHITELIST`` (comma-separated keys given an
``API_RATE_LIMIT_WHITELIST_LIMIT``).
"""

import time
from collections import defaultdict, deque
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings

logger = get_logger(__name__)

_RATE_LIMIT_HEADER = "X-RateLimit-Limit"
_REMAINING_HEADER = "X-RateLimit-Remaining"
_RESET_HEADER = "X-RateLimit-Reset"
_RETRY_AFTER_HEADER = "Retry-After"


class InMemoryRateLimiter:
    """Process-local fixed-window rate limiter (fallback when Redis is absent)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        """Return (allowed, remaining, seconds_until_reset)."""
        now = time.monotonic()
        window_start = now - window_seconds
        hits = self._hits[key]
        while hits and hits[0] <= window_start:
            hits.popleft()
        if len(hits) >= limit:
            reset_in = int(hits[0] + window_seconds - now) + 1
            return False, 0, max(reset_in, 1)
        hits.append(now)
        return True, limit - len(hits), window_seconds


class RedisRateLimiter:
    """Redis-backed fixed-window rate limiter (safe across workers).

    Falls back to a process-local window when Redis is unreachable so the
    limit stays enforced in single-process deployments and development.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis: Any = None
        self._fallback = InMemoryRateLimiter()
        self._redis_healthy = True

    def _client(self) -> Any:
        if self._redis is None:
            import redis.asyncio as redis

            self._redis = redis.from_url(self._redis_url)
        return self._redis

    async def check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        now = int(time.time())
        window_key = f"ratelimit:{key}:{now // window_seconds}"
        try:
            client = self._client()
            count = await client.incr(window_key)
            if count == 1:
                await client.expire(window_key, window_seconds)
            self._redis_healthy = True
            remaining = max(0, limit - int(count))
            reset_in = window_seconds - (now % window_seconds)
            return (int(count) <= limit), remaining, reset_in
        except Exception as exc:
            if self._redis_healthy:
                logger.warning("Redis rate limiter unavailable (%s); using in-memory window", exc)
                self._redis_healthy = False
            return await self._fallback.check(key, limit, window_seconds)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Applies per-identity request limits and adds standard rate headers."""

    def __init__(self, app: Any, limiter: Any | None = None) -> None:
        super().__init__(app)
        self._limiter = limiter or InMemoryRateLimiter()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Never limit health probes or OpenAPI docs.
        path = request.url.path
        if path.startswith("/health") or path in {"/docs", "/redoc", "/openapi.json", "/metrics"}:
            return await call_next(request)

        settings = get_settings()
        limit = settings.api.API_RATE_LIMIT
        identity = self._identity(request)
        window = 60

        allowed, remaining, reset_in = await self._limiter.check(identity, limit, window)

        headers = {
            _RATE_LIMIT_HEADER: str(limit),
            _REMAINING_HEADER: str(remaining),
            _RESET_HEADER: str(reset_in),
        }
        if not allowed:
            headers[_RETRY_AFTER_HEADER] = str(reset_in)
            logger.warning("Rate limit exceeded for %s on %s", identity, path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Retry later."},
                headers=headers,
            )
        response = await call_next(request)
        for header, value in headers.items():
            response.headers[header] = value
        return response

    @staticmethod
    def _identity(request: Request) -> str:
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"key:{api_key[:12]}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"


def _is_coroutine_function(func: Any) -> bool:
    import inspect

    return inspect.iscoroutinefunction(func)


def build_rate_limiter() -> Any:
    """Prefer Redis when a reachable URL is configured, else in-memory."""
    settings = get_settings()
    if settings.redis.REDIS_URL:
        return RedisRateLimiter(settings.redis.REDIS_URL)
    return InMemoryRateLimiter()


__all__ = [
    "InMemoryRateLimiter",
    "RateLimitMiddleware",
    "RedisRateLimiter",
    "build_rate_limiter",
]
