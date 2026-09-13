"""Duplicate detection and version-conflict detection for feed items.

Two layers of deduplication:

* **Batch level** - within one sync run, the same application arriving from
  multiple payloads (or repeated discovery) is collapsed to the freshest,
  most complete entry.
* **Catalog level** - against the database, an item is matched to an existing
  application by ``bundle_id`` first (the strongest cross-platform identity),
  then ``app_id`` (source-qualified repository), then ``slug``.

Version conflicts: when the same application/version already exists with
different asset digests or URLs, that is a *content conflict* (e.g. a
re-published build). Conflicts are reported, never silently overwritten.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.services.feed_sync.schemas import FeedItem
from omnisource.config.logging import get_logger
from omnisource.core.models.application import Application
from omnisource.core.models.release import Release, ReleaseAsset

logger = get_logger(__name__)


@dataclass
class DeduplicationResult:
    """Outcome of batch deduplication."""

    kept: list[FeedItem] = field(default_factory=list)
    removed: list[tuple[FeedItem, str]] = field(default_factory=list)

    @property
    def removed_count(self) -> int:
        return len(self.removed)


def _version_key(version: str) -> tuple[int, ...]:
    """Parse a version into comparable numeric components (semver-ish)."""
    parts: list[int] = []
    for chunk in version.replace("-", ".").split("."):
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts[:4]) or (0,)


def is_version_newer(candidate: str, current: str) -> bool:
    """True when *candidate* sorts strictly after *current*."""
    try:
        return _version_key(candidate) > _version_key(current)
    except Exception:
        return False


class FeedDeduplicator:
    """Collapses duplicate feed items and detects version conflicts."""

    def deduplicate_batch(self, items: list[FeedItem]) -> DeduplicationResult:
        """Collapse duplicates within one batch.

        Identity priority: bundle_id > app_id > slug > repository.
        The freshest item (latest pushed_at, then most releases) wins.
        """

        def identity_keys(entry: FeedItem) -> list[str]:
            keys: list[str] = []
            if entry.bundle_id:
                keys.append(f"bundle:{entry.bundle_id}")
            keys.append(f"app:{entry.app_id}")
            keys.append(f"slug:{entry.slug}")
            keys.append(f"repo:{entry.repository.lower()}")
            return keys

        result = DeduplicationResult()
        index: dict[str, int] = {}  # identity key -> slot in result.kept

        for item in items:
            keys = identity_keys(item)
            slot: int | None = None
            duplicate_reason: str | None = None
            for key in keys:
                known = index.get(key)
                if known is None:
                    continue
                existing = result.kept[known]
                if self._is_fresher(item, existing):
                    result.removed.append((existing, "superseded in batch by fresher payload"))
                    result.kept[known] = item
                    slot = known
                else:
                    duplicate_reason = f"duplicate of {existing.app_id} (matched on {key})"
                break
            if slot is not None:
                for key in keys:
                    index[key] = slot
            elif duplicate_reason is None:
                new_slot = len(result.kept)
                result.kept.append(item)
                for key in keys:
                    index.setdefault(key, new_slot)
            else:
                result.removed.append((item, duplicate_reason))
        return result

    @staticmethod
    def _is_fresher(candidate: FeedItem, current: FeedItem) -> bool:
        candidate_time = candidate.pushed_at
        current_time = current.pushed_at
        if candidate_time is not None and current_time is not None:
            if candidate_time != current_time:
                return candidate_time > current_time
        return len(candidate.releases) > len(current.releases)

    async def find_existing(self, session: AsyncSession, item: FeedItem) -> Application | None:
        """Find the catalog application this feed item maps to, if any."""
        query = select(Application).where(
            or_(
                Application.app_id == item.app_id,
                Application.slug == item.slug,
            )
        )
        if item.bundle_id:
            query = query.where(
                or_(
                    Application.app_id == item.app_id,
                    Application.slug == item.slug,
                    Application.bundle_id == item.bundle_id,
                )
            )
        result = await session.execute(query.limit(1))
        return result.scalars().first()

    async def detect_version_conflicts(
        self, session: AsyncSession, app: Application | None, item: FeedItem
    ) -> list[str]:
        """Compare incoming releases against persisted releases.

        Returns a list of human-readable conflict descriptions. An empty list
        means every incoming release is new or identical.
        """
        if app is None:
            return []
        result = await session.execute(
            select(Release)
            .where(Release.application_id == app.id)
            .options(selectinload(Release.assets).selectinload(ReleaseAsset.asset))
        )
        existing: dict[str, Release] = {
            release.version: release for release in result.scalars().all()
        }

        conflicts: list[str] = []
        for release in item.releases:
            current = existing.get(release.version)
            if current is None:
                continue
            incoming_hashes = {a.sha256 for a in release.assets if a.sha256}
            incoming_urls = {a.url for a in release.assets}
            stored_urls = self._urls_of(current)
            stored_hashes = self._hashes_of(current)
            # A newer build for the same version with different content is a
            # conflict; identical content is a benign re-publish.
            if incoming_urls and stored_urls and not (incoming_urls & stored_urls):
                conflicts.append(
                    f"release {release.version}: asset URLs differ from stored release "
                    "(possible re-published build)"
                )
            elif incoming_hashes and stored_hashes and not (incoming_hashes & stored_hashes):
                conflicts.append(
                    f"release {release.version}: SHA-256 digests differ from stored release"
                )
        return conflicts

    @staticmethod
    def _urls_of(release: Release) -> set[str]:
        """Collection of asset download URLs for a persisted release."""
        urls: set[str] = set()
        for release_asset in release.assets or []:
            asset = release_asset.asset
            if asset is not None and asset.download_url:
                urls.add(asset.download_url)
        return urls

    @staticmethod
    def _hashes_of(release: Release) -> set[str]:
        """Collection of stored SHA-256 digests for a persisted release."""
        hashes: set[str] = set()
        for release_asset in release.assets or []:
            asset = release_asset.asset
            if asset is not None and asset.sha256:
                hashes.add(asset.sha256.lower())
        return hashes


__all__ = ["DeduplicationResult", "FeedDeduplicator", "is_version_newer"]
