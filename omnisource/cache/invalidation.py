"""Automatic cache invalidation by cache tags.

TTLs (see :mod:`omnisource.api.cache`) bound staleness, but writers take the
fast path: when catalogue data changes, the affected tags are purged so the
next request is rebuilt from the database.

Tags:

* ``apps``            - app listing, search results, stats
* ``app:{app_id}``    - single-app detail, trust/security pages
* ``trending``        - trending, popular, latest, stats
* ``categories``      - category taxonomy and per-category listings
* ``recommendations`` - related/recommended app endpoints
* ``feeds``           - signed feed endpoints
"""

from __future__ import annotations

from omnisource.cache.store import get_cache_store
from omnisource.config.logging import get_logger

logger = get_logger(__name__)

TAG_APPS = "apps"
TAG_TRENDING = "trending"
TAG_CATEGORIES = "categories"
TAG_RECOMMENDATIONS = "recommendations"
TAG_FEEDS = "feeds"

_ALL_CATALOGUE_TAGS = (
    TAG_APPS,
    TAG_TRENDING,
    TAG_CATEGORIES,
    TAG_RECOMMENDATIONS,
    TAG_FEEDS,
)


def app_tag(app_id: str) -> str:
    return f"app:{app_id}"


def tags_for_app_change(app_ids: list[str]) -> set[str]:
    """Every tag invalidated when the given applications change."""
    tags: set[str] = {TAG_APPS, TAG_TRENDING, TAG_RECOMMENDATIONS, TAG_CATEGORIES, TAG_FEEDS}
    tags.update(app_tag(app_id) for app_id in app_ids)
    return tags


async def invalidate_tags(tags: set[str] | list[str]) -> int:
    """Invalidate all cache entries registered under *tags*. Returns Redis keys deleted."""
    if not tags:
        return 0
    store = await get_cache_store()
    deleted = await store.delete_tagged_keys(list(tags))
    logger.info("Cache invalidation: tags=%s redis_keys_deleted=%d", sorted(tags), deleted)
    return deleted


async def invalidate_app(app_id: str) -> int:
    """Invalidate everything that may embed this application."""
    return await invalidate_tags(tags_for_app_change([app_id]))


async def invalidate_feed_sync(app_ids: list[str]) -> int:
    """Invalidate after a feed sync published changes."""
    return await invalidate_tags(tags_for_app_change(app_ids))


async def invalidate_all() -> int:
    """Full catalogue invalidation (admin emergency purge)."""
    return await invalidate_tags(set(_ALL_CATALOGUE_TAGS))


__all__ = [
    "TAG_APPS",
    "TAG_CATEGORIES",
    "TAG_FEEDS",
    "TAG_RECOMMENDATIONS",
    "TAG_TRENDING",
    "app_tag",
    "invalidate_all",
    "invalidate_app",
    "invalidate_feed_sync",
    "invalidate_tags",
    "tags_for_app_change",
]
