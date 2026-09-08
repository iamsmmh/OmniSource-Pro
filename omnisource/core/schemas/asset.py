"""Pydantic schemas for downloadable assets."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class AssetStatusSchema(str, Enum):
    """Status of an asset."""

    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    QUARANTINED = "quarantined"
    REVIEW_REQUIRED = "review_required"
    UNKNOWN = "unknown"
    STALE = "stale"
    FAILED = "failed"


class AssetSourceSchema(str, Enum):
    """Source of an asset."""

    GITHUB_RELEASE = "github_release"
    GITHUB_ASSET = "github_asset"
    OFFICIAL = "official"
    MIRROR = "mirror"
    CACHED = "cached"
    OTHER = "other"


class AssetSchema(BaseSchema):
    """Schema for a downloadable asset."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    asset_id: str = Field(..., description="Asset identifier")
    filename: str = Field(..., description="Filename")
    display_name: Optional[str] = Field(default=None, description="Display name")
    description: Optional[str] = Field(default=None, description="Description")
    download_url: str = Field(..., description="Download URL")
    browser_download_url: Optional[str] = Field(default=None, description="Browser download URL")
    mirror_url: Optional[str] = Field(default=None, description="Mirror URL")
    cached_url: Optional[str] = Field(default=None, description="Cached URL")
    size_bytes: Optional[int] = Field(default=None, description="Size in bytes")
    mime_type: Optional[str] = Field(default=None, description="MIME type")
    file_type: Optional[str] = Field(default=None, description="File type")
    detected_platform: Optional[str] = Field(default=None, description="Detected platform")
    detected_architecture: Optional[str] = Field(default=None, description="Detected architecture")
    platform_confidence: float = Field(default=0.0, description="Platform confidence")
    architecture_confidence: float = Field(default=0.0, description="Architecture confidence")
    package_type: Optional[str] = Field(default=None, description="Package type")
    version: Optional[str] = Field(default=None, description="Version")
    sha256: Optional[str] = Field(default=None, description="SHA-256 checksum")
    sha512: Optional[str] = Field(default=None, description="SHA-512 checksum")
    md5: Optional[str] = Field(default=None, description="MD5 checksum")
    status: AssetStatusSchema = Field(default=AssetStatusSchema.PENDING, description="Status")
    source: AssetSourceSchema = Field(default=AssetSourceSchema.OTHER, description="Source")
    validation_status: Optional[str] = Field(default=None, description="Validation status")
    validation_message: Optional[str] = Field(default=None, description="Validation message")
    download_count: int = Field(default=0, description="Download count")
    release_id: Optional[UUID] = Field(default=None, description="Release identifier")
    last_validated_at: Optional[datetime] = Field(default=None, description="Last validated at")
    last_accessed_at: Optional[datetime] = Field(default=None, description="Last accessed at")
    content_hash: Optional[str] = Field(default=None, description="Content hash")
