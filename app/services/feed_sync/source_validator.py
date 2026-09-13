"""Source validation for the feed pipeline.

A source repository is admitted to the catalogue only when it passes every
eligibility rule. Failures are collected (not short-circuited) so operators
can see the full reason set in the sync report.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from omnisource.config.logging import get_logger

logger = get_logger(__name__)

_OWNER_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")


class SourceValidationConfig(BaseModel):
    """Operator-tunable admission rules for source repositories."""

    allow_archived: bool = False
    allow_forks: bool = False
    min_stars: int = Field(ge=0, default=0)
    allowed_owners: list[str] = Field(default_factory=list)
    allowed_owner_domains: list[str] = Field(default_factory=list)
    required_https_urls: bool = True


class SourceValidationResult(BaseModel):
    """Outcome of validating one source repository payload."""

    repository: str | None = None
    ok: bool
    reasons: list[str] = Field(default_factory=list)

    @property
    def first_reason(self) -> str | None:
        return self.reasons[0] if self.reasons else None


class SourceValidator:
    """Validates raw repository payloads against admission rules."""

    def __init__(self, config: SourceValidationConfig | None = None) -> None:
        self.config = config or SourceValidationConfig()

    def validate_repository(self, payload: Any) -> SourceValidationResult:
        """Validate a raw GitHub repository payload.

        Returns a result with *all* violated rules; ``ok`` is True only when
        none are violated.
        """
        if not isinstance(payload, dict):
            return SourceValidationResult(ok=False, reasons=["payload is not an object"])

        full_name = str(payload.get("full_name") or "")
        result = SourceValidationResult(repository=full_name or None, ok=True)
        reasons = result.reasons

        if not full_name:
            reasons.append("missing full_name")
            return result
        if not _OWNER_REPO.match(full_name):
            reasons.append(f"malformed repository name: {full_name!r}")
            return result

        owner = full_name.split("/", 1)[0].lower()

        if self.config.allowed_owners and owner not in {
            o.lower() for o in self.config.allowed_owners
        }:
            reasons.append(f"owner {owner!r} is not in the allowed owner list")
        if self.config.allowed_owner_domains and not any(
            owner == d.lower() or owner.startswith(d.lower().lstrip("@"))
            for d in self.config.allowed_owner_domains
        ):
            reasons.append(f"owner {owner!r} has no allowed domain")

        if payload.get("archived") and not self.config.allow_archived:
            reasons.append("repository is archived")
        if payload.get("fork") and not self.config.allow_forks:
            reasons.append("repository is a fork")

        stars = payload.get("stargazers_count")
        if isinstance(stars, (int, float)) and stars < self.config.min_stars:
            reasons.append(f"stars {stars} below minimum {self.config.min_stars}")

        html_url = str(payload.get("html_url") or "")
        if self.config.required_https_urls and html_url and not html_url.startswith("https://"):
            reasons.append("html_url must be https")

        # A default branch must exist for release syncing to be meaningful.
        if not payload.get("default_branch"):
            reasons.append("repository has no default branch")

        result.ok = not reasons
        if not result.ok:
            logger.info("Source rejected: %s: %s", full_name, "; ".join(reasons))
        return result

    def validate_source_health(self, health: Any) -> SourceValidationResult:
        """Validate the connector health probe for a source."""
        healthy = getattr(health, "healthy", None)
        source = getattr(health, "source", None) or "source"
        if healthy is None:
            return SourceValidationResult(
                repository=str(source), ok=False, reasons=["no health data"]
            )
        if not healthy:
            detail = getattr(health, "detail", None) or "unhealthy"
            return SourceValidationResult(
                repository=str(source), ok=False, reasons=[f"source unhealthy: {detail}"]
            )
        return SourceValidationResult(repository=str(source), ok=True)


__all__ = [
    "SourceValidationConfig",
    "SourceValidationResult",
    "SourceValidator",
]
