"""Pydantic schemas for platforms and architectures."""

from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


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


class PlatformSchema(BaseSchema):
    """Schema for a platform."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    platform_type: str = Field(..., description="Platform type")
    name: str = Field(..., description="Name")
    display_name: str = Field(..., description="Display name")
    description: Optional[str] = Field(default=None, description="Description")
    icon: Optional[str] = Field(default=None, description="Icon")
    is_active: bool = Field(default=True, description="Is active")


class ArchitectureSchema(BaseSchema):
    """Schema for a CPU architecture."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    architecture_type: str = Field(..., description="Architecture type")
    name: str = Field(..., description="Name")
    display_name: str = Field(..., description="Display name")
    description: Optional[str] = Field(default=None, description="Description")
    aliases: List[str] = Field(default_factory=list, description="Aliases")
