"""Base Pydantic schemas for OmniSource."""

from datetime import datetime
from typing import Any, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    """Base schema with common fields and methods."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


T = TypeVar('T', bound=BaseSchema)


class UUIDSchema(BaseSchema):
    """Schema with UUID primary key."""

    id: UUID = Field(..., description="Unique identifier")


class TimestampedSchema(BaseSchema):
    """Schema with timestamps."""

    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class SoftDeletedSchema(BaseSchema):
    """Schema with soft delete flag."""

    is_deleted: bool = Field(default=False, description="Soft delete flag")
