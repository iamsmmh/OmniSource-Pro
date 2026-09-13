"""Job definitions for OmniSource automation."""

from collections.abc import Awaitable, Callable
from typing import Any

from omnisource.automation.jobs.discover import run_discovery
from omnisource.automation.jobs.feed_sync import run_feed_sync
from omnisource.automation.jobs.generate_feeds import run_feed_generation
from omnisource.automation.jobs.index import run_indexing
from omnisource.automation.jobs.recommend import run_recommendation_refresh
from omnisource.automation.jobs.source_health import run_source_health_check
from omnisource.automation.jobs.sync import run_sync
from omnisource.automation.jobs.validate import run_validation
from omnisource.automation.jobs.webhooks import run_webhook_delivery

JobHandler = Callable[..., Awaitable[Any]]

# Maps a job type (string) to its handler function.
JOB_HANDLERS: dict[str, JobHandler] = {
    "discover_repositories": run_discovery,
    "sync_repository": run_sync,
    "sync_releases": run_sync,
    "sync_assets": run_sync,
    "full_sync": run_sync,
    "feed_sync": run_feed_sync,
    "validate_asset": run_validation,
    "index_search": run_indexing,
    "refresh_recommendations": run_recommendation_refresh,
    "health_check": run_source_health_check,
    "generate_feed": run_feed_generation,
    "deliver_webhooks": run_webhook_delivery,
}

__all__ = [
    "JOB_HANDLERS",
    "JobHandler",
    "run_discovery",
    "run_feed_generation",
    "run_feed_sync",
    "run_indexing",
    "run_recommendation_refresh",
    "run_source_health_check",
    "run_sync",
    "run_validation",
    "run_webhook_delivery",
]
