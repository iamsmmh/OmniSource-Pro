"""Release and asset models."""

from datetime import datetime, UTC
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SQLEnum, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base
from omnisource.core.models.repository import Repository
from omnisource.core.models.application import Application


class ReleaseStatus(str, Enum):
    """Status of a release."""

    DRAFT = "draft"
    PRERELEASE = "prerelease"
    RELEASED = "released"
    DEPRECATED = "deprecated"


class PackageType(str, Enum):
    """Package types for different platforms."""

    # iOS
    IPA = "ipa"
    
    # Android
    APK = "apk"
    AAB = "aab"
    
    # Windows
    EXE = "exe"
    MSI = "msi"
    MSIX = "msix"
    APPX = "appx"
    ZIP = "zip"
    
    # macOS
    DMG = "dmg"
    PKG = "pkg"
    
    # Linux
    DEB = "deb"
    RPM = "rpm"
    FLATPAK = "flatpak"
    FLATPAKREF = "flatpakref"
    APPIMAGE = "appimage"
    TAR_GZ = "tar.gz"
    TAR_XZ = "tar.xz"
    SNAP = "snap"
    
    # Other
    BINARY = "binary"
    SOURCE = "source"
    DOCKER = "docker"


# Platform detection rules
ASSET_RULES = {
    "ios": {
        "extensions": [".ipa"],
        "package_types": [PackageType.IPA],
    },
    "android": {
        "extensions": [".apk", ".aab"],
        "package_types": [PackageType.APK, PackageType.AAB],
    },
    "windows": {
        "extensions": [".exe", ".msi", ".msix", ".appx"],
        "package_types": [PackageType.EXE, PackageType.MSI, PackageType.MSIX, PackageType.APPX],
    },
    "macos": {
        "extensions": [".dmg", ".pkg"],
        "package_types": [PackageType.DMG, PackageType.PKG],
    },
    "linux": {
        "extensions": [".appimage", ".deb", ".rpm", ".flatpak", ".flatpakref", ".snap"],
        "package_types": [
            PackageType.APPIMAGE,
            PackageType.DEB,
            PackageType.RPM,
            PackageType.FLATPAK,
            PackageType.FLATPAKREF,
            PackageType.SNAP,
        ],
    },
}


class Release(Base):
    """Represents a software release."""

    __tablename__ = "releases"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    application_id: Mapped[UUID] = mapped_column(
        foreign_key="applications.id", nullable=False, index=True
    )
    repository_id: Mapped[UUID] = mapped_column(
        foreign_key="repositories.id", nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tag: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    body: Mapped[Optional[str]] = mapped_column(Text)
    body_html: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ReleaseStatus] = mapped_column(
        SQLEnum(ReleaseStatus), default=ReleaseStatus.RELEASED, index=True
    )
    is_prerelease: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at_external: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    commit_sha: Mapped[Optional[str]] = mapped_column(String(100))
    commit_url: Mapped[Optional[str]] = mapped_column(String(500))
    tarball_url: Mapped[Optional[str]] = mapped_column(String(500))
    zipball_url: Mapped[Optional[str]] = mapped_column(String(500))
    download_count: Mapped[int] = mapped_column(BigInteger, default=0)

    # Relationships
    application: Mapped[Application] = relationship(
        "Application", back_populates="releases"
    )
    repository: Mapped[Repository] = relationship(
        "Repository", back_populates="releases"
    )
    assets: Mapped[list["ReleaseAsset"]] = relationship(
        "ReleaseAsset", back_populates="release", cascade="all, delete-orphan"
    )
    history: Mapped[list["ReleaseHistory"]] = relationship(
        "ReleaseHistory", back_populates="release", cascade="all, delete-orphan"
    )


class ReleaseAsset(Base):
    """Represents an asset (downloadable file) associated with a release."""

    __tablename__ = "release_assets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    release_id: Mapped[UUID] = mapped_column(
        foreign_key="releases.id", nullable=False, index=True
    )
    asset_id: Mapped[UUID] = mapped_column(
        foreign_key="assets.id", nullable=False, unique=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    release: Mapped[Release] = relationship(
        "Release", back_populates="assets"
    )
    asset: Mapped["Asset"] = relationship(
        "Asset", back_populates="release_assets"
    )


class ReleaseHistory(Base):
    """Tracks changes to a release over time."""

    __tablename__ = "release_history"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    release_id: Mapped[UUID] = mapped_column(
        foreign_key="releases.id", nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    changed_fields: Mapped[list[str]] = mapped_column(String, default=[])
    old_values: Mapped[dict] = mapped_column(String, default={})
    new_values: Mapped[dict] = mapped_column(String, default={})
    changed_by: Mapped[Optional[str]] = mapped_column(String(100))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(UTC), nullable=False
    )

    # Relationships
    release: Mapped[Release] = relationship(
        "Release", back_populates="history"
    )
