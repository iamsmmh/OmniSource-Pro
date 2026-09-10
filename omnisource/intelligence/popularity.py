"""Popularity score calculation."""

import math
from typing import Any


def _log_scale(value: int) -> float:
    """Map a raw count to a 0-1 signal using a logarithmic scale."""
    if value <= 0:
        return 0.0
    return min(1.0, math.log10(value + 1) / 4.0)  # ~10k -> 1.0


def compute_popularity(metrics: dict[str, Any]) -> dict[str, Any]:
    """Compute a popularity score (0-100) and factor breakdown.

    Supported metric keys: ``stars``, ``forks``, ``downloads``,
    ``contributors``, ``omnistore_interactions``.
    """
    stars = _log_scale(int(metrics.get("stars") or 0))
    forks = _log_scale(int(metrics.get("forks") or 0))
    downloads = _log_scale(int(metrics.get("downloads") or 0))
    contributors = _log_scale(int(metrics.get("contributors") or 0))
    omnistore = _log_scale(int(metrics.get("omnistore_interactions") or 0))

    weights = {
        "stars": 0.25,
        "forks": 0.20,
        "downloads": 0.20,
        "contributors": 0.15,
        "activity": 0.10,
        "omnistore": 0.10,
    }

    # "activity" uses the max of stars/downloads as a proxy when unavailable.
    activity = max(stars, downloads)

    factors = {
        "stars": stars,
        "forks": forks,
        "downloads": downloads,
        "contributors": contributors,
        "activity": activity,
        "omnistore": omnistore,
    }

    raw = sum(factors[k] * weights[k] for k in weights)
    normalized = round(max(0.0, min(1.0, raw)) * 100)

    return {
        "score": raw,
        "normalized_score": normalized,
        "factors": {k: round(v, 3) for k, v in factors.items()},
        "github_stars": int(metrics.get("stars") or 0),
        "github_forks": int(metrics.get("forks") or 0),
        "release_downloads": int(metrics.get("downloads") or 0),
        "contributors": int(metrics.get("contributors") or 0),
        "omnistore_interactions": int(metrics.get("omnistore_interactions") or 0),
    }
