"""Pydantic schemas for screenshots."""

from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class ScreenshotSchema(BaseSchema):
    """Schema for an application screenshot."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = Field(default=None, description="Unique identifier")
    application_id: UUID = Field(..., description="Application identifier")
    url: str = Field(..., description="Image URL")
    thumbnail_url: str | None = Field(default=None, description="Thumbnail URL")
    cached_url: str | None = Field(default=None, description="Cached URL")
    caption: str | None = Field(default=None, description="Caption")
    alt_text: str | None = Field(default=None, description="Alt text")
    sort_order: int = Field(default=0, description="Sort order")
    platform_id: UUID | None = Field(default=None, description="Platform identifier")
    width: int | None = Field(default=None, description="Width")
    height: int | None = Field(default=None, description="Height")
    mime_type: str | None = Field(default=None, description="MIME type")
    size_bytes: int | None = Field(default=None, description="Size in bytes")
    is_primary: bool = Field(default=False, description="Is primary")
    is_valid: bool = Field(default=True, description="Is valid")
    validation_message: str | None = Field(default=None, description="Validation message")
