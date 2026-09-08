"""Unified scoring engine."""

from typing import Any, Dict

from omnisource.intelligence.popularity import compute_popularity
from omnisource.intelligence.quality_scoring import compute_quality
from omnisource.intelligence.trust_scoring import compute_trust


class ScoringEngine:
    """Computes trust, quality, and popularity scores for applications."""

    def compute_trust(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        return compute_trust(metrics)

    def compute_quality(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        return compute_quality(metrics)

    def compute_popularity(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        return compute_popularity(metrics)

    def compute_all(self, metrics: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Compute all three scores from a single metrics dictionary."""
        return {
            "trust": compute_trust(metrics),
            "quality": compute_quality(metrics),
            "popularity": compute_popularity(metrics),
        }

    def build_metrics(
        self,
        *,
        open_source: bool = True,
        has_license: bool = False,
        has_readme: bool = False,
        has_description: bool = False,
        stars: int = 0,
        forks: int = 0,
        contributors: int = 0,
        downloads: int = 0,
        has_releases: bool = False,
        release_count: int = 0,
        last_release_days: float | None = None,
        last_activity_days: float | None = None,
        platform_count: int = 0,
        valid_asset_ratio: float = 0.5,
        security_flags: int = 0,
        metadata_completeness: float = 0.7,
        omnistore_interactions: int = 0,
    ) -> Dict[str, Any]:
        """Build a metrics dictionary for the scoring functions."""
        return {
            "open_source": open_source,
            "has_license": has_license,
            "has_readme": has_readme,
            "has_description": has_description,
            "stars": stars,
            "forks": forks,
            "contributors": contributors,
            "downloads": downloads,
            "has_releases": has_releases,
            "release_count": release_count,
            "last_release_days": last_release_days,
            "last_activity_days": last_activity_days,
            "platform_count": platform_count,
            "valid_asset_ratio": valid_asset_ratio,
            "security_flags": security_flags,
            "metadata_completeness": metadata_completeness,
            "omnistore_interactions": omnistore_interactions,
        }
