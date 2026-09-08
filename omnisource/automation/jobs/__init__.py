"""Job definitions for OmniSource automation."""

from typing import Any, Awaitable, Callable, Dict

from omnisource.automation.jobs.discover import run_discovery
from omnisource.automation.jobs.generate_feeds import run_feed_generation
from omnisource.automation.jobs.index import run_indexing
from omnisource.automation.jobs.sync import run_sync
from omnisource.automation.jobs.validate import run_validation

JobHandler = Callable[..., Awaitable[Any]]

# Maps a job type (string) to its handler function.
JOB_HANDLERS: Dict[str, JobHandler] = {
    "discover_repositories": run_discovery,
    "sync_repository": run_sync,
    "sync_releases": run_sync,
    "sync_assets": run_sync,
    "full_sync": run_sync,
    "validate_asset": run_validation,
    "index_search": run_indexing,
    "generate_feed": run_feed_generation,
}

__all__ = [
    "JOB_HANDLERS",
    "JobHandler",
    "run_discovery",
    "run_sync",
    "run_validation",
    "run_indexing",
    "run_feed_generation",
]
