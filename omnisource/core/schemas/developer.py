"""Pydantic schemas for developers and organizations."""

from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class DeveloperSchema(BaseSchema):
    """Schema for a software developer."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = Field(default=None, description="Unique identifier")
    developer_id: str = Field(..., description="Developer identifier")
    slug: str = Field(..., description="Slug")
    name: str = Field(..., description="Name")
    display_name: str | None = Field(default=None, description="Display name")
    email: str | None = Field(default=None, description="Email")
    url: str | None = Field(default=None, description="URL")
    avatar_url: str | None = Field(default=None, description="Avatar URL")
    bio: str | None = Field(default=None, description="Bio")
    location: str | None = Field(default=None, description="Location")


class OrganizationSchema(BaseSchema):
    """Schema for an organization."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = Field(default=None, description="Unique identifier")
    organization_id: str = Field(..., description="Organization identifier")
    slug: str = Field(..., description="Slug")
    name: str = Field(..., description="Name")
    display_name: str | None = Field(default=None, description="Display name")
    description: str | None = Field(default=None, description="Description")
    url: str | None = Field(default=None, description="URL")
    avatar_url: str | None = Field(default=None, description="Avatar URL")
    location: str | None = Field(default=None, description="Location")
    members_count: int | None = Field(default=None, description="Members count")
