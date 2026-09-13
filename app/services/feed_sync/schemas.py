"""Strict Pydantic schemas for the feed pipeline.

Every feed item MUST validate against these models before it may be written
to the database. The models are configured ``extra="forbid"`` at the payload
boundaries so unexpected fields from upstream providers fail loudly instead
of being silently stored.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    """Base model: strict extra fields, case-sensitive, trimmed strings."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


HEX_SHA256 = r"^[0-9a-f]{64}$"
BUNDLE_ID = r"^[a-z0-9][a-z0-9]*(\.[a-z0-9][a-z0-9_-]*){1,5}$"
REPOSITORY = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
VERSION = r"^[A-Za-z0-9][A-Za-z0-9._+\-]{0,49}$"
URL = r"^https?://"

VALID_PLATFORMS = {"android", "ios", "linux", "macos", "windows", "web", "electron"}


class FeedAsset(_StrictModel):
    """A downloadable artifact attached to a release."""

    filename: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=8, max_length=2048)
    size_bytes: int = Field(ge=0, default=0)
    sha256: str | None = Field(default=None, pattern=HEX_SHA256)
    platform: str | None = Field(default=None, max_length=32)
    architecture: str | None = Field(default=None, max_length=32)
    package_type: str | None = Field(default=None, max_length=32)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("asset url must be http(s)")
        return v


class FeedRelease(_StrictModel):
    """A versioned release of a repository."""

    version: str = Field(min_length=1, max_length=50, pattern=VERSION)
    tag: str | None = Field(default=None, max_length=200)
    published_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=20000)
    is_prerelease: bool = False
    assets: list[FeedAsset] = Field(default_factory=list, max_length=100)

    @field_validator("version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        # Leading v/V is tolerated at the boundary and stripped downstream.
        return v


class FeedItem(_StrictModel):
    """One normalized, validated application feed entry."""

    source: str = Field(min_length=1, max_length=50)
    repository: str = Field(min_length=3, max_length=200, pattern=REPOSITORY)
    owner: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)

    app_id: str = Field(min_length=3, max_length=255)
    slug: str = Field(min_length=1, max_length=80)
    bundle_id: str | None = Field(default=None, max_length=255)

    homepage: str | None = Field(default=None, max_length=2048)
    documentation_url: str | None = Field(default=None, max_length=2048)
    license: str | None = Field(default=None, max_length=64)

    tags: list[str] = Field(default_factory=list, max_length=20)
    platforms: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("platforms")
    @classmethod
    def _validate_platforms(cls, v: list[str]) -> list[str]:
        for platform in v:
            if platform not in VALID_PLATFORMS:
                raise ValueError(f"unknown platform: {platform}")
        return v

    releases: list[FeedRelease] = Field(min_length=1, max_length=25)

    stars: int = Field(ge=0, default=0)
    forks: int = Field(ge=0, default=0)
    open_issues: int = Field(ge=0, default=0)
    pushed_at: datetime | None = None
    archived: bool = False
    fork: bool = False

    # Populated by the normalizer; excluded from validation input.
    content_hash: str | None = Field(default=None, pattern=HEX_SHA256)

    @field_validator("homepage", "documentation_url")
    @classmethod
    def _validate_urls(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError("url fields must be http(s)")
        return v

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, v: list[str]) -> list[str]:
        return [t for t in v if 0 < len(t) <= 40]

    def canonical(self) -> dict[str, Any]:
        """Deterministic JSON-safe representation used for content hashing."""
        data = self.model_dump(mode="json")
        data.pop("content_hash", None)
        data["tags"] = sorted(data.get("tags") or [])
        data["platforms"] = sorted(data.get("platforms") or [])
        for release in data.get("releases") or []:
            release["assets"] = sorted(
                release.get("assets") or [], key=lambda a: (a["url"], a["filename"])
            )
        return data


class SyncCheckpoint(_StrictModel):
    """Incremental sync checkpoint for a single repository."""

    source: str
    repository: str
    etag: str | None = None
    last_synced_at: datetime | None = None
    last_version: str | None = None
    last_content_hash: str | None = Field(default=None, pattern=HEX_SHA256)


class FeedStats(_StrictModel):
    """Per-run counters attached to a feed document."""

    fetched: int = 0
    validated: int = 0
    parsed: int = 0
    normalized: int = 0
    duplicates_removed: int = 0
    published: int = 0
    conflicts: int = 0
    failed: int = 0


class FeedDocument(_StrictModel):
    """A signed, exchangeable feed document (subset of the signed feed v1)."""

    source: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: str = "v1"
    items: list[FeedItem] = Field(default_factory=list)
    stats: FeedStats = Field(default_factory=FeedStats)

    def to_feed_entries(self) -> list[dict[str, Any]]:
        """Serialize items into the public signed-feed entry shape."""
        entries = []
        for item in self.items:
            entries.append(
                {
                    "id": item.app_id,
                    "name": item.name,
                    "slug": item.slug,
                    "description": item.description,
                    "bundle_id": item.bundle_id,
                    "repository": f"https://github.com/{item.repository}",
                    "homepage": item.homepage,
                    "license": item.license,
                    "tags": item.tags,
                    "platforms": item.platforms,
                    "latest_version": item.releases[0].version if item.releases else None,
                    "updated_at": (item.pushed_at or datetime.now(UTC)).isoformat(),
                    "assets": [
                        {
                            "filename": asset.filename,
                            "url": asset.url,
                            "size_bytes": asset.size_bytes,
                            "sha256": asset.sha256,
                            "platform": asset.platform,
                            "architecture": asset.architecture,
                            "package_type": asset.package_type,
                        }
                        for release in item.releases[:1]
                        for asset in release.assets
                    ],
                }
            )
        return entries


__all__ = [
    "VALID_PLATFORMS",
    "FeedAsset",
    "FeedDocument",
    "FeedItem",
    "FeedRelease",
    "FeedStats",
    "SyncCheckpoint",
]
