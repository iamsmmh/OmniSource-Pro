"""Asset models for downloadable files."""

from datetime import datetime, UTC
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, JSON, BigInteger, Boolean, DateTime, Enum as SQLEnum, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base
from omnisource.core.models.platform import Platform, Architecture
from omnisource.core.models.release import ReleaseAsset


class AssetStatus(str, Enum):
    """Status of an asset."""

    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    QUARANTINED = "quarantined"
    REVIEW_REQUIRED = "review_required"
    UNKNOWN = "unknown"
    STALE = "stale"
    FAILED = "failed"


class AssetSource(str, Enum):
    """Source of an asset."""

    GITHUB_RELEASE = "github_release"
    GITHUB_ASSET = "github_asset"
    OFFICIAL = "official"
    MIRROR = "mirror"
    CACHED = "cached"
    OTHER = "other"


class MimeType(str, Enum):
    """Common MIME types for software assets."""

    OCTET_STREAM = "application/octet-stream"
    ZIP = "application/zip"
    TAR_GZ = "application/gzip"
    TAR_XZ = "application/x-xz"
    EXE = "application/x-msdownload"
    MSI = "application/x-msi"
    DMG = "application/x-apple-diskimage"
    PKG = "application/x-newton-compatible-pkg"
    DEB = "application/vnd.debian.binary-package"
    RPM = "application/x-rpm"
    APK = "application/vnd.android.package-archive"
    IPA = "application/octet-stream"  # iOS IPA files
    AAB = "application/octet-stream"  # Android App Bundle
    FLATPAK = "application/x-flatpak"
    FLATPAKREF = "application/x-flatpakref"
    APPIMAGE = "application/x-executable"
    MSIX = "application/msix"
    APPX = "application/appx"


class Asset(Base):
    """Represents a downloadable asset (binary, package, etc.)."""

    __tablename__ = "assets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    asset_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(String(500))
    
    # URLs
    download_url: Mapped[str] = mapped_column(String(500), nullable=False)
    browser_download_url: Mapped[Optional[str]] = mapped_column(String(500))
    mirror_url: Mapped[Optional[str]] = mapped_column(String(500))
    cached_url: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Metadata
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    file_type: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Platform and architecture
    platform_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("platforms.id"), index=True
    )
    architecture_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("architectures.id"), index=True
    )
    detected_platform: Mapped[Optional[str]] = mapped_column(String(50))
    detected_architecture: Mapped[Optional[str]] = mapped_column(String(50))
    platform_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    architecture_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Package info
    package_type: Mapped[Optional[str]] = mapped_column(String(50))
    version: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Checksums
    sha256: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    sha512: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    md5: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Status and validation
    status: Mapped[AssetStatus] = mapped_column(
        SQLEnum(AssetStatus), default=AssetStatus.PENDING, index=True
    )
    source: Mapped[AssetSource] = mapped_column(
        SQLEnum(AssetSource), default=AssetSource.OTHER, index=True
    )
    validation_status: Mapped[Optional[str]] = mapped_column(String(50))
    validation_message: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Statistics
    download_count: Mapped[int] = mapped_column(BigInteger, default=0)
    last_validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Content hash for change detection
    content_hash: Mapped[Optional[str]] = mapped_column(String(128), index=True)

    # Relationships
    platform: Mapped[Optional[Platform]] = relationship(
        "Platform", back_populates="assets"
    )
    architecture: Mapped[Optional[Architecture]] = relationship(
        "Architecture", back_populates="assets"
    )
    release_assets: Mapped[list[ReleaseAsset]] = relationship(
        "ReleaseAsset", back_populates="asset", cascade="all, delete-orphan"
    )
    validation: Mapped[Optional["AssetValidation"]] = relationship(
        "AssetValidation", back_populates="asset", uselist=False, cascade="all, delete-orphan"
    )


class AssetValidation(Base):
    """Tracks validation results for an asset."""

    __tablename__ = "asset_validations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id"), nullable=False, unique=True, index=True
    )
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    http_status: Mapped[Optional[int]] = mapped_column(Integer)
    content_length: Mapped[Optional[int]] = mapped_column(BigInteger)
    actual_sha256: Mapped[Optional[str]] = mapped_column(String(128))
    actual_sha512: Mapped[Optional[str]] = mapped_column(String(128))
    actual_mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    validation_errors: Mapped[list[str]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    validated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(UTC), nullable=False
    )
    validated_by: Mapped[Optional[str]] = mapped_column(String(100))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_validation_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    asset: Mapped[Asset] = relationship(
        "Asset", back_populates="validation"
    )
