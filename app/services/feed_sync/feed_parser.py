"""Feed parser: raw provider payloads -> validated :class:`FeedItem`.

The parser is the single point where untrusted upstream data crosses into
the trusted domain. Anything that cannot be represented by the strict
schemas raises :class:`FeedValidationError` with field-level detail, and the
item is rejected before it ever reaches normalization or the database.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from app.services.feed_sync.schemas import FeedAsset, FeedItem, FeedRelease
from omnisource.config.logging import get_logger

logger = get_logger(__name__)

_PLATFORM_KEYWORDS = {
    "android": "android",
    "ios": "ios",
    "ipad": "ios",
    "iphone": "ios",
    "macos": "macos",
    "osx": "macos",
    "darwin": "macos",
    "linux": "linux",
    "windows": "windows",
    "web": "web",
    "electron": "electron",
}
_PACKAGE_KEYWORDS = {
    "appimage": "appimage",
    "deb": "deb",
    "rpm": "rpm",
    "flatpak": "flatpak",
    "snap": "snap",
    "apk": "apk",
    "ipa": "ipa",
    "dmg": "dmg",
    "pkg": "pkg",
    "msi": "msi",
    "exe": "msi",
    "zip": "archive",
    "tar.gz": "archive",
    "tgz": "archive",
    "tar": "archive",
    "brew": "formula",
}
_ARCH_KEYWORDS = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "x64": "x86_64",
    "arm64": "arm64",
    "aarch64": "arm64",
    "arm": "arm",
    "i386": "i386",
    "i686": "i386",
    "universal": "universal",
}

_SHA256_RE = re.compile(r"\bsha256[=: ]([0-9a-f]{64})\b")


class FeedValidationError(Exception):
    """Raised when a raw payload cannot be parsed into a valid FeedItem."""

    def __init__(self, repository: str, field_name: str, reason: str) -> None:
        super().__init__(f"{repository}: {field_name}: {reason}")
        self.repository = repository
        self.field_name = field_name
        self.reason = reason


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _detect_platform(filename: str, mime_type: str | None) -> str | None:
    lowered = filename.lower()
    for keyword, platform in _PLATFORM_KEYWORDS.items():
        if keyword in lowered:
            return platform
    if mime_type:
        lowered_mime = mime_type.lower()
        if "x-ipa" in lowered_mime or "x-mobipocket" in lowered_mime:
            return "ios"
        if "apk" in lowered_mime:
            return "android"
    return None


def _detect_architecture(filename: str) -> str | None:
    lowered = filename.lower()
    for keyword, arch in _ARCH_KEYWORDS.items():
        if f"-{keyword}" in lowered or lowered.startswith(keyword):
            return arch
    return None


def _detect_package_type(filename: str) -> str | None:
    lowered = filename.lower()
    for suffix, package in sorted(_PACKAGE_KEYWORDS.items(), key=lambda kv: -len(kv[0])):
        if lowered.endswith("." + suffix) or lowered.endswith(suffix):
            return package
    return None


def _normalize_platform(platform: str | None) -> str | None:
    if not platform:
        return None
    return _PLATFORM_KEYWORDS.get(platform.lower())


class FeedParser:
    """Parses and strictly validates raw GitHub payloads into FeedItems."""

    def __init__(self, source_name: str = "github") -> None:
        self.source_name = source_name

    # ------------------------------------------------------------------
    # Assets / releases
    # ------------------------------------------------------------------

    def parse_asset(self, raw: Any, repository: str) -> FeedAsset:
        """Parse one raw GitHub release asset."""
        if not isinstance(raw, dict):
            raise FeedValidationError(repository, "asset", "asset is not an object")
        url = raw.get("browser_download_url") or raw.get("url")
        filename = raw.get("name")
        if not url:
            raise FeedValidationError(repository, "asset.url", "missing browser_download_url")
        if not filename:
            filename = str(url).rsplit("/", 1)[-1] or "asset"
        sha256 = raw.get("digest")
        if isinstance(sha256, str) and sha256.upper().startswith("SHA256:"):
            sha256 = sha256.split(":", 1)[1].lower()
        elif isinstance(sha256, str):
            match = _SHA256_RE.search(sha256)
            sha256 = match.group(1) if match else None
        else:
            sha256 = None
        try:
            return FeedAsset(
                filename=str(filename)[:255],
                url=str(url)[:2048],
                size_bytes=int(raw.get("size") or 0),
                sha256=sha256,
                platform=_normalize_platform(_detect_platform(str(filename), None)),
                architecture=_detect_architecture(str(filename)),
                package_type=_detect_package_type(str(filename)),
            )
        except PydanticValidationError as exc:
            first_error = exc.errors()[0] if exc.errors() else {"msg": str(exc)}
            loc = ".".join(str(part) for part in first_error.get("loc", ("asset",)))
            raise FeedValidationError(repository, loc, str(first_error.get("msg", exc))) from exc

    def parse_release(self, raw: Any, repository: str) -> FeedRelease:
        """Parse one raw GitHub release object."""
        if not isinstance(raw, dict):
            raise FeedValidationError(repository, "release", "release is not an object")
        tag = raw.get("tag_name")
        name = raw.get("name") or tag
        version = (tag or name or "").strip().lstrip("vV").strip()
        if not version:
            raise FeedValidationError(repository, "release.version", "release has no version")

        assets: list[FeedAsset] = []
        for raw_asset in (raw.get("assets") or [])[:100]:
            try:
                assets.append(self.parse_asset(raw_asset, repository))
            except FeedValidationError as exc:
                # A malformed asset should not kill the whole release; skip
                # and log, the release itself still carries its version.
                logger.warning("Skipping malformed asset in %s: %s", repository, exc)

        published_at = _parse_datetime(raw.get("published_at") or raw.get("created_at"))
        notes = raw.get("body")
        try:
            return FeedRelease(
                version=version[:50],
                tag=str(tag)[:200] if tag else None,
                published_at=published_at,
                notes=str(notes)[:20000] if notes else None,
                is_prerelease=bool(raw.get("prerelease") or raw.get("draft")),
                assets=assets,
            )
        except PydanticValidationError as exc:
            first_error = exc.errors()[0] if exc.errors() else {"msg": str(exc)}
            loc = ".".join(str(part) for part in first_error.get("loc", ("release",)))
            raise FeedValidationError(repository, loc, str(first_error.get("msg", exc))) from exc

    # ------------------------------------------------------------------
    # Repository -> FeedItem
    # ------------------------------------------------------------------

    def parse_repository(
        self,
        payload: Any,
        releases: list[Any] | None = None,
        license_spdx: str | None = None,
        topics: list[str] | None = None,
        extra_tags: list[str] | None = None,
    ) -> FeedItem:
        """Parse a repository payload plus its releases into a FeedItem."""
        if not isinstance(payload, dict):
            raise FeedValidationError(str(payload), "payload", "repository is not an object")

        repository = str(payload.get("full_name") or "")
        if not repository:
            raise FeedValidationError("unknown", "full_name", "missing full_name")
        owner = repository.split("/", 1)[0]

        name = payload.get("name") or repository.rsplit("/", 1)[-1]
        description = payload.get("description")
        license_info = payload.get("license") or {}
        license_spdx = license_spdx or (
            license_info.get("spdx_id") if isinstance(license_info, dict) else None
        )
        if license_spdx and license_spdx.upper() == "NOASSERTION":
            license_spdx = None

        all_tags = [str(t) for t in (topics or []) if t]
        all_tags += [str(t) for t in (extra_tags or []) if t]
        normalized: list[str] = []
        for tag in all_tags:
            platform = _normalize_platform(tag)
            if platform is not None and platform not in normalized:
                normalized.append(platform)
        platforms = sorted(normalized)

        parsed_releases: list[FeedRelease] = []
        for raw_release in (releases or [])[:25]:
            parsed_releases.append(self.parse_release(raw_release, repository))

        try:
            return FeedItem(
                source=self.source_name,
                repository=repository,
                owner=owner,
                name=str(name)[:200],
                description=str(description)[:5000] if description else None,
                app_id=f"{self.source_name}/{repository}",
                slug=str(name)[:80],
                bundle_id=None,
                homepage=str(payload["html_url"]) if payload.get("html_url") else None,
                documentation_url=str(payload["homepage"]) if payload.get("homepage") else None,
                license=(str(license_spdx)[:64] if license_spdx else None),
                tags=all_tags[:20],
                platforms=platforms,
                releases=parsed_releases,
                stars=int(payload.get("stargazers_count") or 0),
                forks=int(payload.get("forks_count") or 0),
                open_issues=int(payload.get("open_issues_count") or 0),
                pushed_at=_parse_datetime(payload.get("pushed_at")),
                archived=bool(payload.get("archived")),
                fork=bool(payload.get("fork")),
            )
        except PydanticValidationError as exc:
            first_error = exc.errors()[0] if exc.errors() else {"msg": str(exc)}
            loc = ".".join(str(part) for part in first_error.get("loc", ("item",)))
            raise FeedValidationError(repository, loc, str(first_error.get("msg", exc))) from exc

    def parse_feed(self, payload: Any, releases: list[Any] | None = None) -> FeedItem:
        """Parse repository payload + releases (convenience entry point)."""
        return self.parse_repository(payload, releases=releases)


__all__ = ["FeedParser", "FeedValidationError"]
