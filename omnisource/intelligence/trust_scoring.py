"""Trust score calculation."""

from datetime import UTC, datetime
from typing import Any


def _days_since(value: datetime | None) -> float | None:
    if value is None:
        return None
    now = datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return max(0.0, (now - value).total_seconds() / 86400.0)


def compute_trust(metrics: dict[str, Any]) -> dict[str, Any]:
    """Compute a trust score (0-100) and factor breakdown.

    Supported metric keys: ``open_source``, ``has_license``,
    ``stars``, ``contributors``, ``has_releases``, ``last_activity_days``,
    ``valid_asset_ratio``, ``security_flags``, ``has_readme``.
    """
    factors: dict[str, float] = {}

    # License clarity
    factors["license_clarity"] = 1.0 if metrics.get("has_license") else 0.0

    # Open source status
    factors["open_source"] = 1.0 if metrics.get("open_source") else 0.0

    # Repository activity (recency)
    last_activity = metrics.get("last_activity_days")
    if last_activity is None:
        factors["repository_activity"] = 0.5
    elif last_activity <= 30:
        factors["repository_activity"] = 1.0
    elif last_activity <= 180:
        factors["repository_activity"] = 0.7
    elif last_activity <= 365:
        factors["repository_activity"] = 0.4
    else:
        factors["repository_activity"] = 0.1

    # Release consistency
    factors["release_consistency"] = 1.0 if metrics.get("has_releases") else 0.3

    # Contributor diversity
    contributors = int(metrics.get("contributors") or 0)
    if contributors >= 20:
        factors["contributor_diversity"] = 1.0
    elif contributors >= 5:
        factors["contributor_diversity"] = 0.7
    elif contributors >= 1:
        factors["contributor_diversity"] = 0.4
    else:
        factors["contributor_diversity"] = 0.1

    # Issue activity (stars as proxy for community engagement)
    stars = int(metrics.get("stars") or 0)
    if stars >= 1000:
        factors["issue_activity"] = 1.0
    elif stars >= 100:
        factors["issue_activity"] = 0.7
    elif stars >= 10:
        factors["issue_activity"] = 0.4
    else:
        factors["issue_activity"] = 0.2

    # Documentation
    factors["documentation"] = 1.0 if metrics.get("has_readme") else 0.3

    # Asset validation
    factors["asset_validation"] = float(metrics.get("valid_asset_ratio", 0.5))

    # Security signals
    security_flags = int(metrics.get("security_flags") or 0)
    factors["security"] = max(0.0, 1.0 - 0.35 * security_flags)

    # Metadata quality
    factors["metadata_quality"] = float(metrics.get("metadata_quality", 0.7))

    weights = {
        "repository_activity": 0.15,
        "release_consistency": 0.15,
        "license_clarity": 0.10,
        "contributor_diversity": 0.10,
        "issue_activity": 0.05,
        "documentation": 0.05,
        "asset_validation": 0.15,
        "security": 0.20,
        "metadata_quality": 0.05,
        "open_source": 0.05,
    }
    # Re-normalize weights to the factors actually present.
    present_weights = {k: v for k, v in weights.items() if k in factors}
    weight_sum = sum(present_weights.values()) or 1.0

    raw = sum(factors[k] * present_weights[k] for k in present_weights) / weight_sum
    normalized = round(max(0.0, min(1.0, raw)) * 100)

    return {
        "score": raw,
        "normalized_score": normalized,
        "factors": {k: round(v, 3) for k, v in factors.items()},
    }
