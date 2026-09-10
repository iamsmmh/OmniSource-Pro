"""Pydantic schemas for application icons."""

from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class IconSchema(BaseSchema):
    """Schema for an application icon."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = Field(default=None, description="Unique identifier")
    application_id: UUID = Field(..., description="Application identifier")
    url: str = Field(..., description="Icon URL")
    cached_url: str | None = Field(default=None, description="Cached URL")
    thumbnail_url: str | None = Field(default=None, description="Thumbnail URL")
    alt_text: str | None = Field(default=None, description="Alt text")
    sort_order: int = Field(default=0, description="Sort order")
    width: int | None = Field(default=None, description="Width")
    height: int | None = Field(default=None, description="Height")
    mime_type: str | None = Field(default=None, description="MIME type")
    size_bytes: int | None = Field(default=None, description="Size in bytes")
    is_primary: bool = Field(default=False, description="Is primary")
    is_valid: bool = Field(default=True, description="Is valid")
    validation_message: str | None = Field(default=None, description="Validation message")
    background_color: str | None = Field(default=None, description="Background color")
