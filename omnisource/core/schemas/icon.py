"""Pydantic schemas for application icons."""

from typing import Optional
from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class IconSchema(BaseSchema):
    """Schema for an application icon."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    application_id: UUID = Field(..., description="Application identifier")
    url: str = Field(..., description="Icon URL")
    cached_url: Optional[str] = Field(default=None, description="Cached URL")
    thumbnail_url: Optional[str] = Field(default=None, description="Thumbnail URL")
    alt_text: Optional[str] = Field(default=None, description="Alt text")
    sort_order: int = Field(default=0, description="Sort order")
    width: Optional[int] = Field(default=None, description="Width")
    height: Optional[int] = Field(default=None, description="Height")
    mime_type: Optional[str] = Field(default=None, description="MIME type")
    size_bytes: Optional[int] = Field(default=None, description="Size in bytes")
    is_primary: bool = Field(default=False, description="Is primary")
    is_valid: bool = Field(default=True, description="Is valid")
    validation_message: Optional[str] = Field(default=None, description="Validation message")
    background_color: Optional[str] = Field(default=None, description="Background color")
