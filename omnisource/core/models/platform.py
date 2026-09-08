"""Platform and architecture models."""

from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base


class PlatformType(str, Enum):
    """Supported platform types."""

    IOS = "ios"
    IPADOS = "ipados"
    ANDROID = "android"
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


class ArchitectureType(str, Enum):
    """Supported architecture types."""

    ARM64 = "arm64"
    AARCH64 = "aarch64"
    X86_64 = "x86_64"
    AMD64 = "amd64"
    X86 = "x86"
    I386 = "i386"
    UNIVERSAL = "universal"
    UNIVERSAL2 = "universal2"
    ARMV7 = "armv7"
    ANY = "any"


# Architecture aliases for normalization
ARCH_ALIASES = {
    "amd64": "x86_64",
    "x64": "x86_64",
    "x86_64": "x86_64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "i686": "x86",
    "i386": "x86",
    "x86": "x86",
    "universal": "universal",
    "universal2": "universal2",
    "armv7": "armv7",
    "any": "any",
}


def normalize_architecture(arch: str) -> str:
    """Normalize architecture string to standard form."""
    return ARCH_ALIASES.get(arch.lower(), arch.lower())


class Platform(Base):
    """Represents a supported platform."""

    __tablename__ = "platforms"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    platform_type: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    icon: Mapped[Optional[str]] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    applications: Mapped[list["Application"]] = relationship(
        "Application", secondary="application_platforms", back_populates="platforms"
    )
    assets: Mapped[list["Asset"]] = relationship(
        "Asset", back_populates="platform"
    )


class Architecture(Base):
    """Represents a CPU architecture."""

    __tablename__ = "architectures"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    architecture_type: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Relationships
    applications: Mapped[list["Application"]] = relationship(
        "Application", secondary="application_architectures", back_populates="architectures"
    )
    assets: Mapped[list["Asset"]] = relationship(
        "Asset", back_populates="architecture"
    )
