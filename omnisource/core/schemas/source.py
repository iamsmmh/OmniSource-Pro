"""Pydantic schemas for external software sources."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class SourceSchema(BaseSchema):
    """Schema for an external software source."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    name: str = Field(..., description="Source name")
    source_type: str = Field(..., description="Source type (github, gitlab, ...)")
    base_url: str = Field(..., description="Base URL")
    api_url: Optional[str] = Field(default=None, description="API URL")
    description: Optional[str] = Field(default=None, description="Description")
    is_active: bool = Field(default=True, description="Is the source active")


class SourceHealthSchema(BaseSchema):
    """Schema for source health status."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    source_id: UUID = Field(..., description="Source identifier")
    status: str = Field(..., description="Health status")
    latency_ms: Optional[float] = Field(default=None, description="Latency in milliseconds")
    error_rate: float = Field(default=0.0, description="Error rate (0-1)")
    last_check_at: Optional[datetime] = Field(default=None, description="Last check timestamp")
    last_success_at: Optional[datetime] = Field(default=None, description="Last success timestamp")
    last_failure_at: Optional[datetime] = Field(default=None, description="Last failure timestamp")
    consecutive_failures: int = Field(default=0, description="Consecutive failures")
