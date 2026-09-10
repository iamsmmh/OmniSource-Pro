"""Feed generation with atomic publishing."""

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings
from omnisource.core.repositories.application import ApplicationRepository
from omnisource.feeds.platform_feeds import FEED_REGISTRY
from omnisource.feeds.schemas import FeedV1

logger = get_logger(__name__)


class FeedGenerator:
    """Generates platform-specific JSON feeds with atomic file publishing."""

    def __init__(
        self,
        session: AsyncSession,
        output_dir: str | None = None,
    ):
        self.session = session
        settings = get_settings()
        self.output_dir = Path(output_dir or settings.feeds.FEEDS_DIR)
        self.version = settings.feeds.FEEDS_VERSION

    async def generate(self, platform: str = "all") -> dict[str, object]:
        """Generate a feed for a single platform."""
        feed_cls = FEED_REGISTRY.get(platform)
        if feed_cls is None:
            raise ValueError(f"Unknown platform: {platform}")

        repo = ApplicationRepository(self.session)
        apps = await repo.get_all_apps()
        feed = feed_cls()
        filtered = feed.filter(apps)

        envelope = FeedV1(
            version=self.version,
            platform=platform,
            generated_at=datetime.now(UTC).isoformat(),
            total=len(filtered),
            apps=filtered,
        )

        payload = envelope.model_dump_json(indent=2)
        path = self._target_path(platform)
        self._atomic_write(path, payload)

        logger.info("Generated %s feed with %d apps at %s", platform, len(filtered), path)
        return {
            "platform": platform,
            "total": len(filtered),
            "path": str(path),
            "version": self.version,
        }

    async def generate_all(self) -> list[dict[str, object]]:
        """Generate feeds for all registered platforms."""
        results = []
        for platform in FEED_REGISTRY.keys():
            results.append(await self.generate(platform))
        return results

    def _target_path(self, platform: str) -> Path:
        return self.output_dir / self.version / f"{platform}.json"

    def _atomic_write(self, path: Path, payload: str) -> None:
        """Write the payload atomically via a temp file + rename."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".feed-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise


__all__ = ["FeedGenerator"]
