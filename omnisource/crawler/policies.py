"""Processing policies for the ingestion pipeline."""

from dataclasses import dataclass

from omnisource.config.settings import get_settings


@dataclass
class ProcessingPolicies:
    """Tunable policies controlling discovery and ingestion behavior."""

    batch_size: int = 100
    max_repositories: int = 100000
    min_stars: int = 0
    max_releases_per_repo: int = 50
    max_assets_per_release: int = 100
    respect_rate_limits: bool = True

    @classmethod
    def from_settings(cls) -> "ProcessingPolicies":
        settings = get_settings()
        return cls(
            batch_size=settings.DISCOVERY_BATCH_SIZE,
            max_repositories=settings.DISCOVERY_MAX_REPOS,
            min_stars=settings.DISCOVERY_MIN_STARS,
        )


__all__ = ["ProcessingPolicies"]
