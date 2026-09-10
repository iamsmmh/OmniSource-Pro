"""Automation scheduler wiring for OmniSource."""

from typing import Any

from omnisource.automation.jobs import (
    run_discovery,
    run_feed_generation,
    run_indexing,
    run_sync,
    run_validation,
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
        "generate_feeds",
        settings.feeds.FEED_GENERATION_INTERVAL,
        lambda: _run_with_session(run_feed_generation),
    )
    scheduler.add_task("backup", 86400, _run_backup)

    return scheduler


async def _run_backup() -> dict[str, Any]:
    """Daily database + feeds backup cycle."""
    from omnisource.core.backup import run_backup

    return await run_backup()


__all__ = ["AsyncScheduler", "build_default_scheduler"]
