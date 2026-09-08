"""Pydantic schemas for developers and organizations."""

from typing import Optional
from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class DeveloperSchema(BaseSchema):
    """Schema for a software developer."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    developer_id: str = Field(..., description="Developer identifier")
    slug: str = Field(..., description="Slug")
    name: str = Field(..., description="Name")
    display_name: Optional[str] = Field(default=None, description="Display name")
    email: Optional[str] = Field(default=None, description="Email")
    url: Optional[str] = Field(default=None, description="URL")
    avatar_url: Optional[str] = Field(default=None, description="Avatar URL")
    bio: Optional[str] = Field(default=None, description="Bio")
    location: Optional[str] = Field(default=None, description="Location")


class OrganizationSchema(BaseSchema):
    """Schema for an organization."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    organization_id: str = Field(..., description="Organization identifier")
    slug: str = Field(..., description="Slug")
    name: str = Field(..., description="Name")
    display_name: Optional[str] = Field(default=None, description="Display name")
    description: Optional[str] = Field(default=None, description="Description")
    url: Optional[str] = Field(default=None, description="URL")
    avatar_url: Optional[str] = Field(default=None, description="Avatar URL")
    location: Optional[str] = Field(default=None, description="Location")
    members_count: Optional[int] = Field(default=None, description="Members count")
