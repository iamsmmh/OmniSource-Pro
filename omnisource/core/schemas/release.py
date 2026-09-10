"""Pydantic schemas for releases and release assets."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class ReleaseStatusSchema(str, Enum):
    """Status of a release."""

    DRAFT = "draft"
    PRERELEASE = "prerelease"
    RELEASED = "released"
    DEPRECATED = "deprecated"


class PackageTypeSchema(str, Enum):
    """Package types for different platforms."""

    IPA = "ipa"
    APK = "apk"
    AAB = "aab"
    EXE = "exe"
    MSI = "msi"
    MSIX = "msix"
    APPX = "appx"
    ZIP = "zip"
    DMG = "dmg"
    PKG = "pkg"
    DEB = "deb"
    RPM = "rpm"
    FLATPAK = "flatpak"
    FLATPAKREF = "flatpakref"
    APPIMAGE = "appimage"
    TAR_GZ = "tar.gz"
    TAR_XZ = "tar.xz"
    SNAP = "snap"
    BINARY = "binary"
    SOURCE = "source"
    DOCKER = "docker"


class ReleaseSchema(BaseSchema):
    """Schema for a software release."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: UUID | None = Field(default=None, description="Unique identifier")
    external_id: str = Field(..., description="External identifier")
    version: str = Field(..., description="Version string")
    tag: str | None = Field(default=None, description="Tag")
    name: str | None = Field(default=None, description="Name")
    body: str | None = Field(default=None, description="Release notes")
    status: ReleaseStatusSchema = Field(default=ReleaseStatusSchema.RELEASED, description="Status")
    is_prerelease: bool = Field(default=False, description="Is prerelease")
    is_draft: bool = Field(default=False, description="Is draft")
    published_at: datetime | None = Field(default=None, description="Published at")
    created_at_external: datetime | None = Field(default=None, description="External creation time")
    commit_sha: str | None = Field(default=None, description="Commit SHA")
    commit_url: str | None = Field(default=None, description="Commit URL")
    tarball_url: str | None = Field(default=None, description="Tarball URL")
    zipball_url: str | None = Field(default=None, description="Zipball URL")
    download_count: int = Field(default=0, description="Download count")
    repository_id: UUID | None = Field(default=None, description="Repository identifier")
    application_id: UUID | None = Field(default=None, description="Application identifier")
    assets: list[Any] = Field(default_factory=list, description="Release assets (raw)")


class ReleaseAssetSchema(BaseSchema):
    """Schema linking a release to an asset."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = Field(default=None, description="Unique identifier")
    release_id: UUID = Field(..., description="Release identifier")
    asset_id: UUID = Field(..., description="Asset identifier")
    sort_order: int = Field(default=0, description="Sort order")
