"""
OmniStore-compatible Pydantic schemas.

These schemas match the expectations of OmniStore as defined in:
https://github.com/iamsmmh/OmniStore-Pro/src/lib/schemas/omnisource.ts
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


def _normalize_url(value: object) -> object:
    """Normalize a URL field for OmniStore.

    Blank values become None; scheme-less values (e.g. "www.example.com")
    get an https:// prefix so they satisfy the HttpUrl type.
    """
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if not stripped.lower().startswith(("http://", "https://")):
            return f"https://{stripped}"
        return stripped
    return value


class OmniStorePlatform(str, Enum):
    """Supported platforms (matches OmniStore)."""

    IOS = "ios"
    IPADOS = "ipados"
    ANDROID = "android"
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


class OmniStoreArchitecture(str, Enum):
    """Supported architectures (matches OmniStore)."""

    ARM64 = "arm64"
    X86_64 = "x86_64"
    X86 = "x86"
    UNIVERSAL = "universal"
    ANY = "any"


class OmniStoreAssetStatus(str, Enum):
    """Asset status (matches OmniStore)."""

    VALID = "VALID"
    INVALID = "INVALID"
    QUARANTINED = "QUARANTINED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNKNOWN = "UNKNOWN"


class OmniStoreAsset(BaseModel):
    """Asset schema compatible with OmniStore."""

    id: str = Field(..., description="Asset identifier")
    platform: OmniStorePlatform = Field(..., description="Target platform")
    architecture: OmniStoreArchitecture = Field(..., description="Target architecture")
    package_type: str = Field(..., description="Package type (e.g., EXE, APK, DMG)")
    version: str = Field(..., description="Version string")
    url: HttpUrl = Field(..., description="Download URL")
    size_bytes: int | None = Field(default=None, description="File size in bytes")
    sha256: str | None = Field(default=None, description="SHA-256 checksum")
    source: str | None = Field(default=None, description="Source of the asset")
    status: OmniStoreAssetStatus = Field(
        default=OmniStoreAssetStatus.UNKNOWN, description="Asset validation status"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "app-win-x64",
                "platform": "windows",
                "architecture": "x86_64",
                "package_type": "EXE",
                "version": "1.0.0",
                "url": "https://github.com/example/app/releases/download/v1.0.0/app.exe",
                "size_bytes": 12345678,
                "sha256": "abc123...",
                "source": "GitHub Release",
                "status": "VALID",
            }
        }
    )


class OmniStoreRelease(BaseModel):
    """Release schema compatible with OmniStore."""

    version: str = Field(..., description="Version string")
    released_at: str | None = Field(default=None, description="Release date (ISO format)")
    notes: str | None = Field(default=None, description="Release notes")
    assets: list[OmniStoreAsset] = Field(default_factory=list, description="Release assets")
    has_breaking_changes: bool = Field(
        default=False, description="Release may break consumers (semver or notes analysis)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "version": "1.0.0",
                "released_at": "2026-01-01T00:00:00Z",
                "notes": "Initial release",
                "assets": [],
            }
        }
    )


class OmniStoreDeveloper(BaseModel):
    """Developer schema compatible with OmniStore."""

    id: str = Field(..., description="Developer identifier")
    slug: str = Field(..., description="Developer slug")
    name: str = Field(..., description="Developer name")
    url: HttpUrl | None = Field(default=None, description="Developer URL")

    @field_validator("url", mode="before")
    @classmethod
    def _normalize_url_field(cls, v: object) -> object:
        return _normalize_url(v)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "example-dev",
                "slug": "example-dev",
                "name": "Example Developer",
                "url": "https://github.com/example",
            }
        }
    )


class OmniStoreScores(BaseModel):
    """Scores schema compatible with OmniStore."""

    trust: int | None = Field(default=None, ge=0, le=100, description="Trust score (0-100)")
    quality: int | None = Field(default=None, ge=0, le=100, description="Quality score (0-100)")
    popularity: int | None = Field(
        default=None, ge=0, le=100, description="Popularity score (0-100)"
    )
    trust_factors: list[str] | None = Field(
        default=None, description="Factors contributing to trust score"
    )
    quality_factors: list[str] | None = Field(
        default=None, description="Factors contributing to quality score"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "trust": 94,
                "quality": 90,
                "popularity": 92,
                "trust_factors": ["Open-source license", "Active repository", "Recent releases"],
                "quality_factors": ["Documentation", "Release consistency"],
            }
        }
    )


class OmniStoreApp(BaseModel):
    """Application schema compatible with OmniStore."""

    id: str = Field(..., description="Application identifier")
    slug: str = Field(..., description="Application slug")
    name: str = Field(..., description="Application name")
    short_description: str | None = Field(default=None, description="Short description")
    description: str | None = Field(default=None, description="Long description")
    features: list[str] | None = Field(default=None, description="List of features")
    developer: OmniStoreDeveloper | None = Field(default=None, description="Developer information")
    categories: list[str] = Field(default_factory=list, description="Application categories")
    tags: list[str] = Field(default_factory=list, description="Application tags")
    platforms: list[OmniStorePlatform] = Field(
        default_factory=list, description="Supported platforms"
    )
    license: str | None = Field(default=None, description="License (SPDX identifier)")
    homepage: HttpUrl | None = Field(default=None, description="Homepage URL")
    repository: HttpUrl | None = Field(default=None, description="Repository URL")
    documentation: HttpUrl | None = Field(default=None, description="Documentation URL")
    icon: HttpUrl | None = Field(default=None, description="Icon URL")
    screenshots: list[HttpUrl] = Field(default_factory=list, description="Screenshot URLs")
    scores: OmniStoreScores | None = Field(default=None, description="Application scores")
    latest_release: OmniStoreRelease | None = Field(
        default=None, description="Latest release information"
    )
    releases: list[OmniStoreRelease] = Field(default_factory=list, description="All releases")
    alternatives: list[str] = Field(default_factory=list, description="Alternative applications")
    similar: list[str] = Field(default_factory=list, description="Similar applications")
    source_name: str | None = Field(default=None, description="Source name (e.g., GitHub)")
    source_status: str | None = Field(default=None, description="Source status")
    updated_at: str | None = Field(default=None, description="Last update timestamp (ISO format)")
    created_at: str | None = Field(default=None, description="Creation timestamp (ISO format)")
    open_source: bool = Field(default=True, description="Is open source")
    active_development: bool | None = Field(default=None, description="Actively developed")

    @field_validator("homepage", "repository", "documentation", "icon", mode="before")
    @classmethod
    def _normalize_url_fields(cls, v: object) -> object:
        return _normalize_url(v)

    @field_validator("screenshots", mode="before")
    @classmethod
    def _drop_blank_screenshots(cls, v: object) -> object:
        if isinstance(v, (list, tuple)):
            return [u for u in v if not (isinstance(u, str) and not u.strip())]
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "localsend",
                "slug": "localsend",
                "name": "LocalSend",
                "short_description": "Share files to nearby devices without the internet.",
                "description": "LocalSend is a free, open-source app that allows you to securely share files and messages with nearby devices over your local network without an internet connection.",
                "features": [
                    "Cross-platform sharing",
                    "No account required",
                    "End-to-end encryption on LAN",
                ],
                "developer": {
                    "id": "localsend",
                    "slug": "localsend",
                    "name": "LocalSend Contributors",
                    "url": "https://github.com/localsend",
                },
                "categories": ["utilities", "networking"],
                "tags": ["file-transfer", "lan", "privacy"],
                "platforms": ["android", "ios", "windows", "macos", "linux"],
                "license": "Apache-2.0",
                "homepage": "https://localsend.org",
                "repository": "https://github.com/localsend/localsend",
                "documentation": "https://github.com/localsend/localsend#readme",
                "scores": {
                    "trust": 94,
                    "quality": 90,
                    "popularity": 92,
                    "trust_factors": [
                        "Open-source license",
                        "Active repository",
                        "Recent releases",
                        "Established contributors",
                    ],
                    "quality_factors": [
                        "Documentation",
                        "Release consistency",
                        "Metadata completeness",
                    ],
                },
                "open_source": True,
                "active_development": True,
                "source_name": "GitHub",
                "source_status": "Healthy",
                "updated_at": "2026-08-20T00:00:00.000Z",
                "created_at": "2022-12-01T00:00:00.000Z",
                "alternatives": ["syncthing"],
                "similar": ["syncthing", "nextcloud"],
                "latest_release": {
                    "version": "1.16.1",
                    "released_at": "2026-08-20T00:00:00.000Z",
                    "notes": "Bug fixes and platform packaging updates.",
                    "assets": [],
                },
            }
        }
    )


class PaginatedApps(BaseModel):
    """Paginated response for apps list."""

    items: list[OmniStoreApp] = Field(..., description="List of applications")
    total: int = Field(..., description="Total number of applications")
    page: int | None = Field(default=None, description="Current page number")
    freshness: str | None = Field(default=None, description="Data freshness timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"items": [], "total": 0, "page": 1, "freshness": "2026-09-07T00:00:00.000Z"}
        }
    )


# Backwards-compatible aliases (used by omnisource.core.schemas.__init__)
OmniStoreAppSchema = OmniStoreApp
OmniStoreAssetSchema = OmniStoreAsset
OmniStoreReleaseSchema = OmniStoreRelease
OmniStoreDeveloperSchema = OmniStoreDeveloper
OmniStoreScoresSchema = OmniStoreScores
PaginatedAppsSchema = PaginatedApps
