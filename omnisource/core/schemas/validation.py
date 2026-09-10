"""Pydantic schemas for validation results."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class ValidationTypeSchema(str, Enum):
    """Types of validation."""

    URL = "url"
    CHECKSUM = "checksum"
    ASSET = "asset"
    METADATA = "metadata"
    SECURITY = "security"
    LICENSE = "license"
    DEDUPLICATION = "deduplication"


class ValidationStatusSchema(str, Enum):
    """Status of validation."""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class ValidationResultSchema(BaseSchema):
    """Schema for a validation result."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: UUID | None = Field(default=None, description="Unique identifier")
    application_id: UUID | None = Field(default=None, description="Application identifier")
    asset_id: UUID | None = Field(default=None, description="Asset identifier")
    validation_type: str = Field(..., description="Validation type")
    status: str = Field(default="pending", description="Status")
    error_code: str | None = Field(default=None, description="Error code")
    message: str | None = Field(default=None, description="Message")
    details: dict[str, object] = Field(default_factory=dict, description="Details")
    validated_at: datetime | None = Field(default=None, description="Validated at")
    validated_by: str | None = Field(default=None, description="Validated by")
    retry_count: int = Field(default=0, description="Retry count")
    next_retry_at: datetime | None = Field(default=None, description="Next retry at")
    is_retriable: bool = Field(default=True, description="Is retriable")
