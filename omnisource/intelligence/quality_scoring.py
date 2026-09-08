"""Quality score calculation."""

from typing import Any, Dict


def compute_quality(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Compute a quality score (0-100) and factor breakdown.

    Supported metric keys: ``has_readme``, ``has_description``,
    ``has_screenshots``, ``platform_count``, ``release_count``,
    ``last_release_days``, ``has_license``, ``metadata_completeness``.
    """
    factors: Dict[str, float] = {}

    factors["documentation"] = (
        1.0 if metrics.get("has_readme") else 0.3 if metrics.get("has_description") else 0.0
    )

    # Activity
    last_release = metrics.get("last_release_days")
    if last_release is None:
        factors["activity"] = 0.5
    elif last_release <= 90:
        factors["activity"] = 1.0
    elif last_release <= 365:
        factors["activity"] = 0.6
    else:
        factors["activity"] = 0.2

    # Release frequency
    release_count = int(metrics.get("release_count") or 0)
    if release_count >= 10:
        factors["release_frequency"] = 1.0
    elif release_count >= 3:
        factors["release_frequency"] = 0.7
    elif release_count >= 1:
        factors["release_frequency"] = 0.4
    else:
        factors["release_frequency"] = 0.1

    # Platform coverage
    platforms = int(metrics.get("platform_count") or 0)
    factors["platform_coverage"] = min(1.0, platforms / 3.0)

    # Metadata completeness
    factors["metadata_completeness"] = float(metrics.get("metadata_completeness", 0.7))

    # Community activity
    stars = int(metrics.get("stars") or 0)
    if stars >= 1000:
        factors["community_activity"] = 1.0
    elif stars >= 100:
        factors["community_activity"] = 0.6
    elif stars >= 10:
        factors["community_activity"] = 0.35
    else:
        factors["community_activity"] = 0.1

    # Maintenance status
    factors["maintenance_status"] = 1.0 if metrics.get("has_releases") else 0.3

    weights = {
        "documentation": 0.15,
        "activity": 0.15,
        "release_frequency": 0.15,
        "platform_coverage": 0.15,
        "metadata_completeness": 0.15,
        "community_activity": 0.15,
        "maintenance_status": 0.10,
    }

    raw = sum(factors[k] * weights[k] for k in weights if k in factors)
    normalized = round(max(0.0, min(1.0, raw)) * 100)

    return {
        "score": raw,
        "normalized_score": normalized,
        "factors": {k: round(v, 3) for k, v in factors.items()},
    }
