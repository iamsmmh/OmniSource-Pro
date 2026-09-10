"""Pydantic schemas for applications."""

from enum import Enum
from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class ApplicationStatusSchema(str, Enum):
    """Status of an application."""

    DRAFT = "draft"
    PUBLISHED = "published"
    QUARANTINED = "quarantined"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


class OpenSourceStatusSchema(str, Enum):
    """Open source status of an application."""

    OPEN_SOURCE = "open_source"
    SOURCE_AVAILABLE = "source_available"
    UNKNOWN = "unknown"
    NOT_OPEN_SOURCE = "not_open_source"
    REVIEW_REQUIRED = "review_required"


class ApplicationSchema(BaseSchema):
    """Schema for a software application."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: UUID | None = Field(default=None, description="Unique identifier")
    app_id: str = Field(..., description="Application identifier")
    slug: str = Field(..., description="Slug")
    name: str = Field(..., description="Name")
    short_description: str | None = Field(default=None, description="Short description")
    long_description: str | None = Field(default=None, description="Long description")
    homepage: str | None = Field(default=None, description="Homepage URL")
    documentation_url: str | None = Field(default=None, description="Documentation URL")
    status: ApplicationStatusSchema = Field(
        default=ApplicationStatusSchema.DRAFT, description="Status"
    )
    open_source_status: OpenSourceStatusSchema = Field(
        default=OpenSourceStatusSchema.UNKNOWN, description="Open source status"
    )
    is_active: bool = Field(default=True, description="Is active")
    is_featured: bool = Field(default=False, description="Is featured")


class ApplicationRelationshipSchema(BaseSchema):
    """Schema for a relationship between applications."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: UUID | None = Field(default=None, description="Unique identifier")
    from_app_id: UUID = Field(..., description="Source application identifier")
    to_app_id: UUID = Field(..., description="Target application identifier")
    relationship_type: str = Field(..., description="Relationship type")
    confidence: float = Field(default=0.0, description="Confidence (0-1)")
    method: str | None = Field(default=None, description="Detection method")
    created_by: str | None = Field(default=None, description="Creator")
