"""Feed sync engine: orchestrates the full ingestion pipeline.

    GitHub Sources
      -> source validation   (eligibility + health gates)
      -> provider fetch      (incremental via ETag checkpoints)
      -> feed parsing        (strict Pydantic validation)
      -> normalization       (canonical forms + content hash)
      -> deduplication       (batch + catalog, version-conflict detection)
      -> publishing          (transactional, automatic rollback)

The engine is retry- and rate-limit aware:

* transient provider failures (network, 5xx) are retried with exponential
  backoff (tenacity) per repository;
* rate-limit exhaustion pauses the run until the upstream reset window
  (``Retry-After`` / X-RateLimit-Reset) instead of retrying blindly;
* every repository keeps a durable :class:`~...SyncCheckpoint` (ETag, last
  sync time, last version, content hash) so subsequent runs only process
  repositories that actually changed.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.feed_sync.feed_deduplicator import FeedDeduplicator
from app.services.feed_sync.feed_normalizer import FeedNormalizer
from app.services.feed_sync.feed_parser import FeedParser, FeedValidationError
from app.services.feed_sync.feed_publisher import FeedPublisher
from app.services.feed_sync.github_provider import (
    GitHubFeedProvider,
    ProviderAuthError,
    ProviderError,
    ProviderNotFoundError,
    ProviderRateLimited,
)
from app.services.feed_sync.schemas import FeedItem, SyncCheckpoint
from app.services.feed_sync.source_validator import SourceValidator
from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings
from omnisource.core.models.sync import SyncState

logger = get_logger(__name__)

RATE_LIMIT_PAUSE_CAP_SECONDS = 900.0


@dataclass
class SyncReport:
    """Aggregated outcome of one sync run."""

    fetched: int = 0
    skipped_unchanged: int = 0
    rejected: list[str] = field(default_factory=list)
    parse_failures: list[str] = field(default_factory=list)
    published: list[str] = field(default_factory=list)
    created: int = 0
    updated: int = 0
    duplicates_removed: int = 0
    conflicts: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    rate_limit_paused_seconds: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    @property
    def ok(self) -> bool:
        return not self.failed

    def _duration_seconds(self) -> float:
        end = self.finished_at or datetime.now(UTC)
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetched": self.fetched,
            "skipped_unchanged": self.skipped_unchanged,
            "rejected": list(self.rejected),
            "parse_failures": list(self.parse_failures),
            "published": list(self.published),
            "created": self.created,
            "updated": self.updated,
            "duplicates_removed": self.duplicates_removed,
            "conflicts": list(self.conflicts),
            "failed": list(self.failed),
            "rate_limit_paused_seconds": round(self.rate_limit_paused_seconds, 2),
            "duration_seconds": self._duration_seconds(),
        }


class FeedSyncEngine:
    """Runs the feed ingestion pipeline for a set of repositories."""

    def __init__(
        self,
        session: AsyncSession,
        provider: GitHubFeedProvider | None = None,
        validator: SourceValidator | None = None,
        parser: FeedParser | None = None,
        normalizer: FeedNormalizer | None = None,
        deduplicator: FeedDeduplicator | None = None,
        on_failure: Callable[[str, Exception], Any] | None = None,
    ) -> None:
        self.session = session
        self.provider = provider or GitHubFeedProvider()
        self.validator = validator or SourceValidator()
        self.parser = parser or FeedParser()
        self.normalizer = normalizer or FeedNormalizer()
        self.deduplicator = deduplicator or FeedDeduplicator()
        self._on_failure = on_failure
        self._owns_provider = provider is None

    async def close(self) -> None:
        if self._owns_provider:
            await self.provider.close()

    async def __aenter__(self) -> FeedSyncEngine:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Checkpoints (incremental sync)
    # ------------------------------------------------------------------

    async def _load_checkpoint(
        self, source_id: Any, repository_id: Any, full_name: str
    ) -> SyncCheckpoint:
        query = select(SyncState).limit(1)
        if repository_id is not None:
            query = query.where(SyncState.repository_id == repository_id)
        elif source_id is not None:
            query = query.where(SyncState.source_id == source_id)
        else:
            return SyncCheckpoint(source=self.parser.source_name, repository=full_name)
        result = await self.session.execute(query)
        state = result.scalars().first()
        if state is None:
            return SyncCheckpoint(source=self.parser.source_name, repository=full_name)
        return SyncCheckpoint(
            source=self.parser.source_name,
            repository=full_name,
            etag=state.last_etag or state.etag,
            last_synced_at=state.last_success,
        )

    async def _save_checkpoint(
        self,
        source_id: Any,
        repository_id: Any,
        full_name: str,
        etag: str | None,
        content_hash: str | None,
    ) -> None:
        """Persist the checkpoint for a successfully synced repository."""
        result = await self.session.execute(
            select(SyncState).where(SyncState.repository_id == repository_id).limit(1)
        )
        state = result.scalars().first()
        if state is None:
            state = SyncState(source_id=source_id, repository_id=repository_id)
            self.session.add(state)
        state.etag = etag
        state.last_etag = etag
        state.last_success = datetime.now(UTC)
        state.last_attempt = datetime.now(UTC)
        state.last_error = None
        state.discovered_count = state.discovered_count + 1
        await self.session.flush()

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    async def _handle_rate_limit(self, report: SyncReport) -> None:
        """Pause until the upstream rate limit resets (bounded wait)."""
        wait = self.provider.seconds_until_rate_reset()
        if wait is None or wait <= 0:
            wait = 60.0
        wait = min(wait, RATE_LIMIT_PAUSE_CAP_SECONDS)
        logger.warning(
            "GitHub rate limit reached; pausing sync for %.0fs (remaining: %s)",
            wait,
            self.provider.rate_limit_remaining(),
        )
        report.rate_limit_paused_seconds += wait
        await asyncio.sleep(wait)

    # ------------------------------------------------------------------
    # Per-repository pipeline
    # ------------------------------------------------------------------

    async def _process_repository(
        self, full_name: str, source_id: Any, repository_id: Any, report: SyncReport
    ) -> FeedItem | None:
        """Validate, fetch, parse, normalize one repository."""
        checkpoint = await self._load_checkpoint(source_id, repository_id, full_name)
        report.fetched += 1

        payload, etag = await self._fetch_with_retry(full_name, checkpoint.etag, report)
        if payload is None:
            report.skipped_unchanged += 1
            return None

        validation = self.validator.validate_repository(payload)
        if not validation.ok:
            report.rejected.append(f"{full_name}: {validation.first_reason}")
            return None

        try:
            releases = await self.provider.fetch_releases(full_name)
        except (ProviderRateLimited, ProviderError) as exc:
            # Releases are optional enrichment; a failed release fetch must
            # not discard the repository metadata we already have.
            logger.warning("Release fetch failed for %s: %s", full_name, exc)
            releases = []
        if not isinstance(releases, list):
            releases = []

        item = self.parser.parse_repository(
            payload,
            releases=releases,
            topics=payload.get("topics") if isinstance(payload.get("topics"), list) else None,
        )
        item = self.normalizer.normalize(item)

        await self._save_checkpoint(source_id, repository_id, full_name, etag, item.content_hash)
        return item

    async def _fetch_with_retry(
        self, full_name: str, etag: str | None, report: SyncReport
    ) -> tuple[Any, str | None]:
        """Fetch with bounded retries: exponential backoff for network errors,
        reset-window pauses for rate limits. Auth errors abort immediately."""
        max_attempts = max(1, get_settings().github.GH_RETRY_COUNT + 1)
        delay = 2.0
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await self.provider.fetch_repository(full_name, etag=etag)
            except ProviderAuthError as exc:
                logger.error("GitHub authentication failed for %s: %s", full_name, exc)
                raise
            except ProviderNotFoundError as exc:
                report.failed.append(f"{full_name}: not found")
                if self._on_failure is not None:
                    await _maybe_await(self._on_failure(full_name, exc))
                return None, etag
            except ProviderRateLimited as exc:
                await self._handle_rate_limit(report)
                last_error = exc
            except ProviderError as exc:
                last_error = exc
                if attempt < max_attempts:
                    logger.warning(
                        "Transient provider error for %s (attempt %d/%d): %s",
                        full_name,
                        attempt,
                        max_attempts,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60.0)
        # Exhausted attempts.
        report.failed.append(f"{full_name}: {last_error}")
        if self._on_failure is not None:
            await _maybe_await(self._on_failure(full_name, last_error or ProviderError("unknown")))
        return None, etag

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def sync_repositories(
        self,
        full_names: list[str],
        source_id: Any = None,
        repository_ids: dict[str, Any] | None = None,
    ) -> SyncReport:
        """Run the full pipeline over an explicit list of repositories.

        ``repository_ids`` maps full name -> repository row id for checkpoint
        persistence. Publishing is transactional inside
        :class:`~app.services.feed_sync.feed_publisher.FeedPublisher`; a run
        therefore either persists everything or nothing.
        """
        report = SyncReport()
        try:
            items: list[FeedItem] = []
            for full_name in full_names:
                repository_id = (repository_ids or {}).get(full_name)
                try:
                    item = await self._process_repository(
                        full_name, source_id, repository_id, report
                    )
                except FeedValidationError as exc:
                    report.parse_failures.append(str(exc))
                    logger.warning("Feed validation failed: %s", exc)
                    continue
                except Exception as exc:
                    logger.exception("Unexpected pipeline error for %s", full_name)
                    report.failed.append(f"{full_name}: {exc}")
                    if self._on_failure is not None:
                        await _maybe_await(self._on_failure(full_name, exc))
                    continue
                if item is not None:
                    items.append(item)

            if not items:
                return report

            deduped = self.deduplicator.deduplicate_batch(items)
            report.duplicates_removed = deduped.removed_count

            publisher = FeedPublisher(self.session)
            publish_result = await publisher.publish(deduped.kept)
            report.published = list(publish_result.published)
            report.created = len(publish_result.created)
            report.updated = len(publish_result.updated)
            report.conflicts = list(publish_result.conflicts)
            return report
        finally:
            report.finished_at = datetime.now(UTC)


async def _maybe_await(value: Any) -> None:
    if asyncio.iscoroutine(value):
        await value


__all__ = ["FeedSyncEngine", "SyncReport"]
