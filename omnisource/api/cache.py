"""Response cache and ETag middleware for public catalogue endpoints."""

import asyncio
import base64
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings

logger = get_logger(__name__)

_CACHEABLE_PREFIXES = (
    "/api/v1/apps",
    "/api/v1/search",
    "/api/v1/releases",
    "/api/v1/categories",
    "/api/v1/platforms",
    "/api/v1/developers",
    "/api/v1/trending",
    "/api/v1/latest",
    "/api/v1/stats",
    "/api/v1/recommendations",
    "/api/v1/trust",
    "/api/v1/security",
    "/feeds/",
)


@dataclass(frozen=True)
class CachedResponse:
    status: int
    headers: list[tuple[bytes, bytes]]
    body: bytes
    expires_at: float


class ResponseCacheStore:
    """Bounded in-process cache with an optional Redis replica.

    The process-local tier prevents network cache availability from becoming a
    request dependency. Redis extends hit rates safely across API replicas;
    errors only disable that tier and are never propagated to clients.
    """

    def __init__(self, max_entries: int = 2000) -> None:
        self._entries: OrderedDict[str, CachedResponse] = OrderedDict()
        self._max_entries = max_entries
        self._redis: Any = None
        self._redis_disabled = False
        self._lock = asyncio.Lock()

    @staticmethod
    def _redis_key(key: str) -> str:
        return "omnisource:response:" + hashlib.sha256(key.encode("utf-8")).hexdigest()

    async def _redis_client(self) -> Any | None:
        if self._redis_disabled:
            return None
        if self._redis is None:
            redis_url = get_settings().redis.REDIS_URL
            if not redis_url:
                self._redis_disabled = True
                return None
            try:
                import redis.asyncio as redis

                self._redis = redis.from_url(
                    redis_url, socket_connect_timeout=0.05, socket_timeout=0.05
                )
            except Exception:
                self._redis_disabled = True
                return None
        return self._redis

    async def get(self, key: str) -> CachedResponse | None:
        now = time.monotonic()
        async with self._lock:
            cached = self._entries.get(key)
            if cached and cached.expires_at > now:
                self._entries.move_to_end(key)
                return cached
            if cached:
                self._entries.pop(key, None)
        client = await self._redis_client()
        if client is None:
            return None
        try:
            raw = await client.get(self._redis_key(key))
            if raw is None:
                return None
            encoded = json.loads(raw)
            ttl = max(1, int(encoded["expires_unix"] - time.time()))
            cached = CachedResponse(
                status=int(encoded["status"]),
                headers=[
                    (base64.b64decode(key), base64.b64decode(value))
                    for key, value in encoded["headers"]
                ],
                body=base64.b64decode(encoded["body"]),
                expires_at=time.monotonic() + ttl,
            )
            async with self._lock:
                self._put_memory(key, cached)
            return cached
        except Exception as exc:
            self._disable_redis(exc)
            return None

    async def set(self, key: str, response: CachedResponse, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        async with self._lock:
            self._put_memory(key, response)
        client = await self._redis_client()
        if client is None:
            return
        try:
            serialized = json.dumps(
                {
                    "status": response.status,
                    "headers": [
                        (
                            base64.b64encode(key).decode("ascii"),
                            base64.b64encode(value).decode("ascii"),
                        )
                        for key, value in response.headers
                    ],
                    "body": base64.b64encode(response.body).decode("ascii"),
                    "expires_unix": time.time() + ttl_seconds,
                },
                separators=(",", ":"),
            )
            await client.setex(self._redis_key(key), ttl_seconds, serialized)
        except Exception as exc:
            self._disable_redis(exc)

    def _put_memory(self, key: str, response: CachedResponse) -> None:
        self._entries[key] = response
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def _disable_redis(self, exc: Exception) -> None:
        if not self._redis_disabled:
            logger.warning("Response-cache Redis tier unavailable; using local cache: %s", exc)
        self._redis_disabled = True


class ResponseCacheMiddleware:
    """Cache anonymous GET responses and serve strong ETags/304s for CDN clients."""

    def __init__(self, app: ASGIApp, store: ResponseCacheStore | None = None) -> None:
        self.app = app
        self.store = store or ResponseCacheStore()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._is_cacheable(scope):
            await self.app(scope, receive, send)
            return
        key = self._key(scope)
        cached = await self.store.get(key)
        if cached is not None:
            await self._send_cached(scope, send, cached)
            return

        messages: list[Message] = []

        async def capture(message: Message) -> None:
            messages.append(message)

        await self.app(scope, receive, capture)
        start = next(
            (message for message in messages if message["type"] == "http.response.start"), None
        )
        bodies = [
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        ]
        if start is None:
            for message in messages:
                await send(message)
            return
        body = b"".join(bodies)
        headers = list(start.get("headers", []))
        status_code = int(start["status"])
        content_type = dict(headers).get(b"content-type", b"")
        if status_code == 200 and b"application/json" in content_type and len(body) <= 2_000_000:
            etag = self._etag(body)
            headers = self._replace_header(headers, b"etag", etag.encode("ascii"))
            ttl = self._ttl(scope)
            headers = self._replace_header(
                headers, b"cache-control", f"public, max-age={ttl}, s-maxage={ttl}".encode("ascii")
            )
            cached = CachedResponse(
                status=status_code,
                headers=headers,
                body=body,
                expires_at=time.monotonic() + ttl,
            )
            await self.store.set(key, cached, ttl)
            await self._send_cached(scope, send, cached)
            return

        await send({"type": "http.response.start", "status": status_code, "headers": headers})
        await send({"type": "http.response.body", "body": body, "more_body": False})

    @staticmethod
    def _is_cacheable(scope: Scope) -> bool:
        if scope["method"] != "GET":
            return False
        path = scope["path"]
        headers = dict(scope.get("headers", []))
        return (
            path.startswith(_CACHEABLE_PREFIXES)
            and b"authorization" not in headers
            and b"x-api-key" not in headers
            and b"x-omnistore-subject" not in headers
        )

    @staticmethod
    def _key(scope: Scope) -> str:
        query = scope.get("query_string", b"").decode("latin-1")
        headers = dict(scope.get("headers", []))
        language = headers.get(b"accept-language", b"").decode("latin-1")
        return f"{scope['path']}?{query}|lang={language}"

    @staticmethod
    def _ttl(scope: Scope) -> int:
        settings = get_settings()
        return (
            settings.api.API_SEARCH_CACHE_TTL
            if scope["path"].startswith("/api/v1/search")
            else settings.api.API_RESPONSE_CACHE_TTL
        )

    @staticmethod
    def _etag(body: bytes) -> str:
        return '"' + hashlib.sha256(body).hexdigest() + '"'

    @staticmethod
    def _replace_header(
        headers: list[tuple[bytes, bytes]], name: bytes, value: bytes
    ) -> list[tuple[bytes, bytes]]:
        return [(key, old) for key, old in headers if key.lower() != name] + [(name, value)]

    async def _send_cached(self, scope: Scope, send: Send, cached: CachedResponse) -> None:
        headers = dict(scope.get("headers", []))
        etag = dict(cached.headers).get(b"etag")
        if etag and headers.get(b"if-none-match") == etag:
            await send(
                {
                    "type": "http.response.start",
                    "status": 304,
                    "headers": [
                        (b"etag", etag),
                        (b"cache-control", dict(cached.headers).get(b"cache-control", b"public")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return
        await send(
            {"type": "http.response.start", "status": cached.status, "headers": cached.headers}
        )
        await send({"type": "http.response.body", "body": cached.body, "more_body": False})


__all__ = ["ResponseCacheMiddleware", "ResponseCacheStore"]
