"""Shared two-tier response cache store with cache-tag registration.

Tier 1 is a bounded process-local LRU so a Redis outage never becomes a
request dependency. Tier 2 (optional) is Redis, which extends hit rates
across API replicas and carries the *cache-tag registry*: every cached
response key is registered under the tags that should invalidate it, which
lets writers purge exactly the entries their change affects.

A module-level singleton (:func:`get_cache_store`) is shared by the API
middleware and the invalidation service so both tiers see the same state
inside one process.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings

logger = get_logger(__name__)

RESPONSE_KEY_PREFIX = "omnisource:response:"
TAG_KEY_PREFIX = "omnisource:cache:tags:"


def response_key(key: str) -> str:
    """Canonical Redis key for a logical cache key."""
    return RESPONSE_KEY_PREFIX + hashlib.sha256(key.encode("utf-8")).hexdigest()


def tag_key(tag: str) -> str:
    return TAG_KEY_PREFIX + tag


@dataclass(frozen=True)
class CachedResponse:
    status: int
    headers: list[tuple[bytes, bytes]]
    body: bytes
    expires_at: float


class ResponseCacheStore:
    """Bounded in-process cache with an optional Redis replica and tag registry."""

    def __init__(self, max_entries: int = 2000) -> None:
        self._entries: OrderedDict[str, CachedResponse] = OrderedDict()
        self._max_entries = max_entries
        self._redis: Any = None
        self._redis_disabled = False
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Redis tier
    # ------------------------------------------------------------------

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
                    redis_url, socket_connect_timeout=0.05, socket_timeout=0.25
                )
            except Exception:
                self._redis_disabled = True
                return None
        return self._redis

    def _disable_redis(self, exc: Exception) -> None:
        if not self._redis_disabled:
            logger.warning("Cache Redis tier unavailable; using local cache: %s", exc)
        self._redis_disabled = True

    # ------------------------------------------------------------------
    # Get / set
    # ------------------------------------------------------------------

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
            raw = await client.get(response_key(key))
            if raw is None:
                return None
            encoded = json.loads(raw)
            ttl = max(1, int(encoded["expires_unix"] - time.time()))
            cached = CachedResponse(
                status=int(encoded["status"]),
                headers=[
                    (base64.b64decode(name), base64.b64decode(value))
                    for name, value in encoded["headers"]
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

    async def set(
        self, key: str, response: CachedResponse, ttl_seconds: int, tags: list[str] | None = None
    ) -> None:
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
                            base64.b64encode(name).decode("ascii"),
                            base64.b64encode(value).decode("ascii"),
                        )
                        for name, value in response.headers
                    ],
                    "body": base64.b64encode(response.body).decode("ascii"),
                    "expires_unix": time.time() + ttl_seconds,
                },
                separators=(",", ":"),
            )
            pipe = client.pipeline()
            pipe.setex(response_key(key), ttl_seconds, serialized)
            for tag in tags or []:
                pipe.sadd(tag_key(tag), response_key(key))
                pipe.expire(tag_key(tag), ttl_seconds)
            await pipe.execute()
        except Exception as exc:
            self._disable_redis(exc)

    def _put_memory(self, key: str, response: CachedResponse) -> None:
        self._entries[key] = response
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def clear_local(self) -> int:
        """Drop every locally cached entry. Returns how many were dropped."""
        count = len(self._entries)
        self._entries.clear()
        return count

    async def delete_tagged_keys(self, tags: list[str]) -> int:
        """Delete every cached response registered under *tags* (Redis tier).

        Also clears the local tier because other tags of this process may
        share entries; the local tier is small and cheap to rebuild.
        Returns the number of Redis keys deleted.
        """
        self.clear_local()
        client = await self._redis_client()
        if client is None or not tags:
            return 0
        deleted = 0
        try:
            pipe = client.pipeline()
            for tag in tags:
                pipe.smemembers(tag_key(tag))
            results = await pipe.execute()
            keys: set[str] = set()
            for members in results:
                keys.update(members)
            if keys:
                pipe2 = client.pipeline()
                pipe2.delete(*keys)
                for tag in tags:
                    pipe2.delete(tag_key(tag))
                outcomes = await pipe2.execute()
                deleted = int(outcomes[0]) if outcomes and isinstance(outcomes[0], int) else 0
            return deleted
        except Exception as exc:
            self._disable_redis(exc)
            return 0


_store_instance: ResponseCacheStore | None = None
_store_lock = asyncio.Lock()


async def get_cache_store() -> ResponseCacheStore:
    """Process-wide cache store shared by middleware and invalidation."""
    global _store_instance
    if _store_instance is None:
        async with _store_lock:
            if _store_instance is None:
                _store_instance = ResponseCacheStore()
    return _store_instance


__all__ = ["CachedResponse", "ResponseCacheStore", "get_cache_store", "response_key", "tag_key"]
