"""Atomic, signed multi-channel feed generation."""

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings
from omnisource.core.models.source import Source
from omnisource.core.repositories.application import ApplicationRepository
from omnisource.feeds.platform_feeds import FEED_REGISTRY
from omnisource.feeds.schemas import FeedV1
from omnisource.feeds.signing import FeedSignatureError, FeedSigner

logger = get_logger(__name__)

FEED_CHANNELS = ("stable", "beta", "nightly", "experimental")


class FeedGenerator:
    """Generates platform-specific, Ed25519-signed JSON feeds atomically."""

    def __init__(
        self, session: AsyncSession, output_dir: str | None = None, signer: FeedSigner | None = None
    ):
        self.session = session
        settings = get_settings()
        self.output_dir = Path(output_dir or settings.feeds.FEEDS_DIR)
        self.version = settings.feeds.FEEDS_VERSION
        self.signer = signer or FeedSigner()

    async def build(self, platform: str = "all", channel: str = "stable") -> FeedV1:
        """Build and locally verify one signed feed envelope before publishing."""
        if platform not in FEED_REGISTRY:
            raise ValueError(f"Unknown platform: {platform}")
        if channel not in FEED_CHANNELS:
            raise ValueError(f"Unknown feed channel: {channel}")

        apps = await ApplicationRepository(self.session).get_all_apps()
        filtered = FEED_REGISTRY[platform]().filter(apps)
        filtered = self._filter_channel(filtered, channel)
        source_count = int(
            await self.session.scalar(
                select(func.count()).select_from(Source).where(Source.is_active.is_(True))
            )
            or 0
        )
        envelope = FeedV1(
            version=self.version,
            platform=platform,
            channel=channel,
            generated_at=datetime.now(UTC).isoformat(),
            total=len(filtered),
            source_count=source_count,
            package_count=len(filtered),
            signing_key=self.signer.public_key_base64,
            apps=filtered,
        )
        signed = self.signer.sign(envelope.model_dump(mode="json"))
        if not self.signer.verify(signed):
            raise FeedSignatureError(
                "refusing to publish feed that failed local signature verification"
            )
        return FeedV1.model_validate(signed)

    @staticmethod
    def _filter_channel(apps, channel: str):
        if channel == "stable":
            prerelease_markers = ("alpha", "beta", "nightly", "preview", "rc")
            return [
                app
                for app in apps
                if app.latest_release is None
                or not any(
                    marker in app.latest_release.version.lower() for marker in prerelease_markers
                )
            ]
        if channel == "beta":
            return [
                app
                for app in apps
                if any(
                    "beta" in release.version.lower() or "rc" in release.version.lower()
                    for release in app.releases
                )
            ]
        if channel == "nightly":
            return [app for app in apps if any("nightly" in tag.lower() for tag in app.tags)]
        # Experimental includes projects that have not reached a strong trust threshold.
        return [
            app
            for app in apps
            if app.scores is None or app.scores.trust is None or app.scores.trust < 60
        ]

    async def generate(self, platform: str = "all", channel: str = "stable") -> dict[str, object]:
        """Generate and atomically publish a single verified channel feed."""
        feed = await self.build(platform, channel)
        payload = feed.model_dump_json(indent=2)
        path = self._target_path(platform, channel)
        self._atomic_write(path, payload)
        # The old stable path remains as a compatibility alias for OmniStore clients.
        if channel == "stable":
            self._atomic_write(self.output_dir / self.version / f"{platform}.json", payload)
        logger.info(
            "Generated signed %s/%s feed with %d apps at %s", channel, platform, feed.total, path
        )
        return {
            "platform": platform,
            "channel": channel,
            "total": feed.total,
            "path": str(path),
            "version": self.version,
            "sha256": feed.sha256,
        }

    async def generate_all(
        self, channels: tuple[str, ...] = FEED_CHANNELS
    ) -> list[dict[str, object]]:
        """Generate every platform feed for each requested release channel."""
        return [
            await self.generate(platform, channel)
            for channel in channels
            for platform in FEED_REGISTRY
        ]

    def _target_path(self, platform: str, channel: str) -> Path:
        return self.output_dir / self.version / channel / f"{platform}.json"

    @staticmethod
    def _atomic_write(path: Path, payload: str) -> None:
        """Write one fully verified payload via temp file + atomic rename."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".feed-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise


__all__ = ["FEED_CHANNELS", "FeedGenerator"]
