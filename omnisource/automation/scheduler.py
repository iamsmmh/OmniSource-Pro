"""Automation scheduler wiring for OmniSource."""

from typing import Any

from omnisource.automation.jobs import (
    run_discovery,
    run_feed_generation,
    run_feed_sync,
    run_indexing,
    run_recommendation_refresh,
    run_source_health_check,
    run_sync,
    run_validation,
    run_webhook_delivery,
)
from omnisource.config.settings import get_settings
from omnisource.core.database.session import create_session
from omnisource.crawler.scheduler import AsyncScheduler


async def _run_with_session(fn, **kwargs) -> dict[str, Any]:
    """Execute a job function with its own database session."""
    async with create_session() as session:
        return await fn(session, **kwargs)


def build_default_scheduler() -> AsyncScheduler:
    """Build a scheduler pre-configured with the standard pipeline tasks."""
    settings = get_settings()
    scheduler = AsyncScheduler()

    sync_interval = settings.SYNC_INTERVAL_HOURS * 3600
    validation_interval = settings.VALIDATION_INTERVAL_HOURS * 3600

    scheduler.add_task(
        "discover",
        sync_interval,
        lambda: _run_with_session(run_discovery, source_type="github"),
    )
    scheduler.add_task(
        "sync",
        sync_interval,
        lambda: _run_with_session(run_sync, source_type="github"),
    )
    scheduler.add_task(
        "discover_fmhy",
        sync_interval,
        lambda: _run_with_session(run_discovery, source_type="fmhy"),
    )
    scheduler.add_task(
        "sync_fmhy",
        sync_interval,
        lambda: _run_with_session(run_sync, source_type="fmhy"),
    )
    scheduler.add_task(
        "validate",
        validation_interval,
        lambda: _run_with_session(run_validation),
    )
    scheduler.add_task(
        "index",
        sync_interval,
        lambda: _run_with_session(run_indexing),
    )
    scheduler.add_task(
        "recommendations",
        sync_interval,
        lambda: _run_with_session(run_recommendation_refresh),
    )
    scheduler.add_task(
        "source_health",
        settings.sources.SOURCE_HEALTH_CHECK_INTERVAL,
        lambda: _run_with_session(run_source_health_check),
    )
    scheduler.add_task(
        "generate_feeds",
        settings.feeds.FEED_GENERATION_INTERVAL,
        lambda: _run_with_session(run_feed_generation),
    )
    scheduler.add_task(
        "feed_sync",
        sync_interval,
        lambda: _run_with_session(run_feed_sync, source_type="github"),
    )
    scheduler.add_task(
        "webhook_delivery",
        60,
        lambda: _run_with_session(run_webhook_delivery),
    )
    scheduler.add_task(
        "materialized_views",
        900,  # 15 minutes: keep trending/featured/recent/most-downloaded fresh
        lambda: _run_with_session(_run_materialized_view_refresh),
    )
    scheduler.add_task(
        "security_profiles",
        6 * 3600,
        lambda: _run_with_session(_run_security_profile_refresh),
    )
    scheduler.add_task("backup", 86400, _run_backup)

    return scheduler


async def _run_backup() -> dict[str, Any]:
    """Daily database + feeds backup cycle."""
    from omnisource.core.backup import run_backup

    return await run_backup()


async def _run_materialized_view_refresh(session) -> dict[str, Any]:
    """Refresh the catalogue materialized views (PostgreSQL)."""
    from omnisource.core.repositories.catalog import CatalogRepository

    return await CatalogRepository(session).refresh_materialized_views()


async def _run_security_profile_refresh(session) -> dict[str, Any]:
    """Refresh all application security (trust) profiles."""
    from omnisource.intelligence.security_profiles import refresh_all_profiles

    return await refresh_all_profiles(session)


__all__ = ["AsyncScheduler", "build_default_scheduler"]
