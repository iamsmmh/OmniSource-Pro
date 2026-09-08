"""Pydantic schemas for categories and tags."""

from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class CategoryType(str, Enum):
    """Standard category types."""

    AUDIO = "audio"
    VIDEO = "video"
    PHOTOGRAPHY = "photography"
    GRAPHICS = "graphics"
    PRODUCTIVITY = "productivity"
    DEVELOPER_TOOLS = "developer-tools"
    EDUCATION = "education"
    COMMUNICATION = "communication"
    SOCIAL = "social"
    INTERNET = "internet"
    BROWSERS = "browsers"
    SECURITY = "security"
    NETWORKING = "networking"
    UTILITIES = "utilities"
    GAMING = "gaming"
    BOOKS = "books"
    FINANCE = "finance"
    SCIENCE = "science"
    SYSTEM_TOOLS = "system-tools"
    AI = "ai"
    OTHER = "other"


class CategorySchema(BaseSchema):
    """Schema for an application category."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    category_type: str = Field(..., description="Category type")
    name: str = Field(..., description="Name")
    slug: str = Field(..., description="Slug")
    description: Optional[str] = Field(default=None, description="Description")
    icon: Optional[str] = Field(default=None, description="Icon")
    parent_id: Optional[UUID] = Field(default=None, description="Parent category identifier")
    sort_order: int = Field(default=0, description="Sort order")
    is_active: bool = Field(default=True, description="Is active")


class TagSchema(BaseSchema):
    """Schema for an application tag."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    name: str = Field(..., description="Name")
    slug: str = Field(..., description="Slug")
    description: Optional[str] = Field(default=None, description="Description")
    usage_count: int = Field(default=0, description="Usage count")
    is_active: bool = Field(default=True, description="Is active")
