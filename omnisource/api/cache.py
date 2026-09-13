"""Response cache and ETag middleware for public catalogue endpoints.

Caching policy (Phase 8):

==============================  ======  =====================================
Resource                        TTL     Cache tags
==============================  ======  =====================================
Trending / popular / latest     5 min   trending, apps
Categories / platforms /        15 min  categories, apps
developers / recommendations
App detail                      1 h     app:{id}, apps, trending,
                                        recommendations, categories, feeds
App list                        60 s    apps, trending, categories,
                                        recommendations, feeds
Search                          30 s    apps, categories, recommendations
Feeds                           60 s    feeds
==============================  ======  =====================================

Writes (feed sync, admin actions, analytics ingest) purge the affected tags
via :mod:`omnisource.cache.invalidation`, so the next request rebuilds from
PostgreSQL. ETag/304 support lets CDN clients avoid re-downloading unchanged
bodies.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from omnisource.cache.store import CachedResponse, get_cache_store
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
    "/api/v1/popular",
    "/api/v1/stats",
    "/api/v1/recommendations",
    "/api/v1/trust",
    "/api/v1/security",
    "/feeds/",
)

# TTL tiers (seconds)
TTL_TRENDING = 300  # 5 minutes
TTL_CATEGORIES = 900  # 15 minutes
TTL_APP_DETAIL = 3600  # 1 hour
TTL_DEFAULT = 60


def _tags_for(path: str) -> list[str]:
    from omnisource.cache import invalidation as inv

    if path.startswith("/api/v1/apps/"):
        app_id = path[len("/api/v1/apps/") :].split("/", 1)[0]
        if app_id and not app_id.startswith(("featured", "recent", "most-downloaded")):
            return [
                inv.app_tag(app_id),
                inv.TAG_APPS,
                inv.TAG_TRENDING,
                inv.TAG_RECOMMENDATIONS,
                inv.TAG_CATEGORIES,
                inv.TAG_FEEDS,
            ]
        return [
            inv.TAG_APPS,
            inv.TAG_TRENDING,
            inv.TAG_RECOMMENDATIONS,
            inv.TAG_CATEGORIES,
            inv.TAG_FEEDS,
        ]
    if path.startswith(("/api/v1/trending", "/api/v1/latest", "/api/v1/popular", "/api/v1/stats")):
        return [inv.TAG_TRENDING, inv.TAG_APPS]
    if path.startswith(("/api/v1/categories", "/api/v1/platforms", "/api/v1/developers")):
        return [inv.TAG_CATEGORIES, inv.TAG_APPS]
    if path.startswith("/api/v1/recommendations"):
        return [inv.TAG_RECOMMENDATIONS, inv.TAG_APPS]
    if path.startswith(("/api/v1/trust/", "/api/v1/security/")):
        app_id = path.rsplit("/", 1)[-1]
        return [inv.app_tag(app_id), inv.TAG_APPS]
    if path.startswith("/feeds/"):
        return [inv.TAG_FEEDS]
    if path.startswith("/api/v1/releases"):
        return [inv.TAG_APPS, inv.TAG_FEEDS]
    return [inv.TAG_APPS]


def _ttl_for(path: str) -> int:
    settings = get_settings()
    if path.startswith("/api/v1/search"):
        return settings.api.API_SEARCH_CACHE_TTL
    if path.startswith(("/api/v1/trending", "/api/v1/latest", "/api/v1/popular", "/api/v1/stats")):
        return TTL_TRENDING
    if path.startswith(
        ("/api/v1/categories", "/api/v1/platforms", "/api/v1/developers", "/api/v1/recommendations")
    ):
        return TTL_CATEGORIES
    if path.startswith("/api/v1/apps/"):
        return TTL_APP_DETAIL
    return TTL_DEFAULT


class ResponseCacheMiddleware:
    """Cache anonymous GET responses with per-resource TTLs, ETags, and 304s."""

    def __init__(self, app: ASGIApp, store: Any | None = None) -> None:
        self.app = app
        self._store_override = store

    async def _store(self) -> Any:
        if self._store_override is not None:
            return self._store_override
        return await get_cache_store()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._is_cacheable(scope):
            await self.app(scope, receive, send)
            return
        key = self._key(scope)
        store = await self._store()
        cached = await store.get(key)
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
            ttl = _ttl_for(scope["path"])
            headers = self._replace_header(
                headers,
                b"cache-control",
                f"public, max-age={ttl}, s-maxage={ttl}".encode("ascii"),
            )
            cached_response = CachedResponse(
                status=status_code,
                headers=headers,
                body=body,
                expires_at=time.monotonic() + ttl,
            )
            await store.set(key, cached_response, ttl, tags=_tags_for(scope["path"]))
            await self._send_cached(scope, send, cached_response)
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
    def _etag(body: bytes) -> str:
        return '"' + hashlib.sha256(body).hexdigest() + '"'

    @staticmethod
    def _replace_header(
        headers: list[tuple[bytes, bytes]], name: bytes, value: bytes
    ) -> list[tuple[bytes, bytes]]:
        kept = [(key, old) for key, old in headers if key.lower() != name]
        kept.append((name, value))
        return kept

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


__all__ = ["TTL_APP_DETAIL", "TTL_CATEGORIES", "TTL_TRENDING", "ResponseCacheMiddleware"]
