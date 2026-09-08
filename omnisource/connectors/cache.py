"""
Response cache for API connectors.
"""

from datetime import datetime, timedelta, UTC
from typing import Any, Dict, Optional

import httpx
from httpx import Response

from omnisource.config.settings import get_settings
from omnisource.config.logging import get_logger

logger = get_logger(__name__)


class ResponseCache:
    """
    Simple in-memory cache for HTTP responses.
    
    Supports TTL-based expiration and automatic invalidation.
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: timedelta = timedelta(minutes=5),
    ):
        """
        Initialize the cache.
        
        Args:
            max_size: Maximum number of cached responses
            default_ttl: Default time-to-live for cached items
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: Dict[str, tuple[Response, datetime]] = {}
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Response]:
        """
        Get a cached response.
        
        Args:
            key: Cache key
            
        Returns:
            Cached response or None if not found or expired
        """
        if key not in self._cache:
            self._misses += 1
            return None
        
        response, cached_at = self._cache[key]
        ttl = self._get_ttl(response)
        
        if datetime.now(UTC) - cached_at > ttl:
            # Expired
            del self._cache[key]
            self._misses += 1
            return None
        
        self._hits += 1
        return response

    def set(self, key: str, response: Response) -> None:
        """
        Cache a response.
        
        Args:
            key: Cache key
            response: HTTP response to cache
        """
        # Don't cache errors or non-200 responses
        if response.status_code != 200:
            return
        
        # Evict old entries if at capacity
        if len(self._cache) >= self.max_size:
            self._evict_oldest()
        
        self._cache[key] = (response, datetime.now(UTC))

    def invalidate(self, key: str) -> bool:
        """
        Invalidate a cached entry.
        
        Args:
            key: Cache key
            
        Returns:
            True if entry was invalidated, False if not found
        """
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def invalidate_all(self) -> int:
        """
        Invalidate all cached entries.
        
        Returns:
            Number of entries invalidated
        """
        count = len(self._cache)
        self._cache.clear()
        return count

    def _get_ttl(self, response: Response) -> timedelta:
        """
        Get TTL for a cached response.
        
        Args:
            response: HTTP response
            
        Returns:
            Time-to-live duration
        """
        # Check for Cache-Control header
        cache_control = response.headers.get("Cache-Control", "")
        
        if "max-age=" in cache_control:
            parts = cache_control.split(",")
            for part in parts:
                if "max-age=" in part:
                    try:
                        max_age = int(part.split("=")[1].strip())
                        return timedelta(seconds=max_age)
                    except (ValueError, IndexError):
                        pass
        
        # Use default TTL
        return self.default_ttl

    def _evict_oldest(self) -> None:
        """Evict the oldest entry from the cache."""
        if not self._cache:
            return
        
        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
        del self._cache[oldest_key]

    @property
    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        """Get cache hit rate."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
