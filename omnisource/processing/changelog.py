"""Changelog analysis: semver parsing and breaking-change detection.

Used by the sync pipeline to flag releases that may break consumers, and by
the API to expose ``has_breaking_changes`` on releases. Two signals are
combined:

1. **Version signals** — a major-version bump (semver), or a minor bump while
   in 0.x (where minor bumps commonly break), or a loss of numeric segments.
2. **Release-notes signals** - conventional-commit keywords
   (``BREAKING CHANGE:``, ``breaking:``, ``feat!:``, ``!:``) and common
   migration-warning phrases.
"""

import re
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

_SEMVER_RE = re.compile(
    r"""^v?
    (?P<major>0|[1-9]\d*)
    \.(?P<minor>0|[1-9]\d*)
    \.(?P<patch>0|[1-9]\d*)
    (?:-(?P<pre>[0-9A-Za-z.-]+))?
    (?:\+(?P<build>[0-9A-Za-z.-]+))?
    $""",
    re.VERBOSE,
)

_BREAKING_PATTERNS = [
    re.compile(r"breaking[ -]?change", re.IGNORECASE),
    re.compile(r"^breaking\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\bbackwards?[ -]incompatible\b", re.IGNORECASE),
    re.compile(r"\bBC break\b", re.IGNORECASE),
    re.compile(r"\bfeat![:\s(]", re.IGNORECASE),
    re.compile(r"\brefactor![:\s(]", re.IGNORECASE),
    re.compile(r"\bfix![:\s(]", re.IGNORECASE),
    re.compile(r"!\s*:", re.MULTILINE),
    re.compile(r"\bmigration required\b", re.IGNORECASE),
    re.compile(r"\bno longer (?:supported|compatible)\b", re.IGNORECASE),
    re.compile(r"\bremoved (?:the )?(?:support|api|feature)\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class Version:
    """A parsed semantic version."""

    major: int
    minor: int
    patch: int
    prerelease: str | None = None
    build: str | None = None
    raw: str = ""

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)


def parse_version(value: str | None) -> Version | None:
    """Parse a semver string (tolerates a leading ``v``); None if not semver."""
    if not value:
        return None
    value = value.strip()
    match = _SEMVER_RE.match(value)
    if not match:
        return None
    return Version(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch")),
        prerelease=match.group("pre"),
        build=match.group("build"),
        raw=value,
    )


def is_breaking_bump(old: str | None, new: str | None) -> bool:
    """Detect a breaking version transition.

    Rules:
    - missing/unparseable versions → not breaking (insufficient information)
    - major bump → breaking
    - minor bump on 0.x → breaking (0.x convention)
    - equal or downgrade → not breaking
    """
    old_v = parse_version(old)
    new_v = parse_version(new)
    if old_v is None or new_v is None:
        return False
    if new_v.major > old_v.major:
        return True
    if old_v.major == 0 and new_v.major == 0 and new_v.minor > old_v.minor:
        return True
    return False


def notes_suggest_breaking(notes: str | None) -> bool:
    """Detect breaking-change language in release notes."""
    if not notes:
        return False
    return any(pattern.search(notes) for pattern in _BREAKING_PATTERNS)


def analyze_release(
    previous_version: str | None,
    release_version: str | None,
    release_notes: str | None = None,
) -> dict[str, Any]:
    """Produce the changelog analysis stored alongside a release.

    Returns ``{"has_breaking_changes": bool, "signals": [...],
    "parsed_version": {...}|None}``.
    """
    signals: list[str] = []

    if is_breaking_bump(previous_version, release_version):
        old_v = parse_version(previous_version)
        new_v = parse_version(release_version)
        if old_v and new_v and new_v.major > old_v.major:
            signals.append("major_version_bump")
        else:
            signals.append("minor_bump_on_0x")

    if notes_suggest_breaking(release_notes):
        signals.append("breaking_notes")

    parsed = parse_version(release_version)
    return {
        "has_breaking_changes": bool(signals),
        "signals": signals,
        "parsed_version": (
            {
                "major": parsed.major,
                "minor": parsed.minor,
                "patch": parsed.patch,
                "prerelease": parsed.prerelease,
            }
            if parsed
            else None
        ),
    }


def summarize_range(versions: list[str]) -> dict[str, Any]:
    """Summarize a version list (newest last) into changelog statistics."""
    breaking_count = 0
    parsed_count = 0
    for old, new in pairwise(versions):
        if is_breaking_bump(old, new):
            breaking_count += 1
    for version in versions:
        if parse_version(version) is not None:
            parsed_count += 1
    return {
        "total": len(versions),
        "parsed_semver": parsed_count,
        "breaking_transitions": breaking_count,
    }


__all__ = [
    "Version",
    "analyze_release",
    "is_breaking_bump",
    "notes_suggest_breaking",
    "parse_version",
    "summarize_range",
]
