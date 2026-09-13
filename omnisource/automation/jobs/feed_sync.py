"""Feed sync job: runs the Phase 1 ingestion pipeline as an automation task.

Pipeline: GitHub sources -> sync engine -> validation -> parsing ->
normalization -> deduplication -> transactional publish (PostgreSQL) with
webhook emission (``feed_synced``) on completion.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.api.metrics import SYNC_REPOSITORIES, SYNC_RUNS
from omnisource.config.logging import get_logger
from omnisource.core.models.repository import Repository
from omnisource.core.models.source import Source
from omnisource.webhooks.delivery import emit_event

logger = get_logger(__name__)


async def run_feed_sync(
    session: AsyncSession,
    source_type: str = "github",
    repositories: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Sync a source through the feed pipeline.

    ``repositories`` (explicit full names) is used for webhook-triggered
    incremental syncs; otherwise every known repository of the source is
    processed (incremental via ETag checkpoints - unchanged repositories cost
    a single 304 request each).
    """
    from app.services.feed_sync.sync_engine import FeedSyncEngine

    source_result = await session.execute(select(Source).where(Source.source_type == source_type))
    source = source_result.scalars().first()

    if repositories is None:
        query = select(Repository).limit(5000)
        if source is not None:
            query = query.where(Repository.source_id == source.id)
        rows = (await session.execute(query)).scalars().all()
        full_names = [repo.full_name for repo in rows if repo.full_name]
        repository_ids = {repo.full_name: repo.id for repo in rows if repo.full_name}
    else:
        full_names = list(repositories)
        query = select(Repository).where(Repository.full_name.in_(full_names))
        rows = (await session.execute(query)).scalars().all()
        repository_ids = {repo.full_name: repo.id for repo in rows}

    if not full_names:
        logger.info("Feed sync: no repositories for source %s", source_type)
        return {"fetched": 0, "skipped": True}

    engine = FeedSyncEngine(session)
    try:
        report = await engine.sync_repositories(
            full_names,
            source_id=source.id if source else None,
            repository_ids=repository_ids,
        )
    finally:
        await engine.close()

    status = "completed" if report.ok else "failed"
    SYNC_RUNS.labels(source=source_type, status=status).inc()
    SYNC_REPOSITORIES.labels(outcome="published").inc(len(report.published))
    SYNC_REPOSITORIES.labels(outcome="unchanged").inc(report.skipped_unchanged)
    SYNC_REPOSITORIES.labels(outcome="failed").inc(len(report.failed))
    if report.conflicts:
        SYNC_REPOSITORIES.labels(outcome="conflict").inc(len(report.conflicts))
    if report.duplicates_removed:
        SYNC_REPOSITORIES.labels(outcome="duplicate").inc(report.duplicates_removed)

    # feed_synced: OmniStore clients refresh on this event.
    try:
        await emit_event(
            session,
            "feed_synced",
            {"source": source_type, **report.to_dict()},
        )
    except Exception:
        logger.warning("feed_synced webhook emission failed", exc_info=True)

    logger.info("Feed sync finished: %s", report.to_dict())
    return report.to_dict()


__all__ = ["run_feed_sync"]
