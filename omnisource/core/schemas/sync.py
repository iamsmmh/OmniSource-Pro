"""Pydantic schemas for sync state and jobs."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class SyncJobTypeSchema(str, Enum):
    """Types of sync jobs."""

    DISCOVER_REPOSITORIES = "discover_repositories"
    SYNC_REPOSITORY = "sync_repository"
    SYNC_RELEASES = "sync_releases"
    SYNC_ASSETS = "sync_assets"
    EXTRACT_METADATA = "extract_metadata"
    VALIDATE_ASSET = "validate_asset"
    CALCULATE_SCORES = "calculate_scores"
    CLASSIFY_APP = "classify_app"
    DEDUPLICATE = "deduplicate"
    INDEX_SEARCH = "index_search"
    GENERATE_FEED = "generate_feed"
    HEALTH_CHECK = "health_check"
    CLEANUP = "cleanup"
    FULL_SYNC = "full_sync"


class SyncJobStatusSchema(str, Enum):
    """Status of a sync job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class SyncStateSchema(BaseSchema):
    """Schema for synchronization state."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    source_id: Optional[UUID] = Field(default=None, description="Source identifier")
    repository_id: Optional[UUID] = Field(default=None, description="Repository identifier")
    cursor: Optional[str] = Field(default=None, description="Pagination cursor")
    last_success: Optional[datetime] = Field(default=None, description="Last success")
    last_attempt: Optional[datetime] = Field(default=None, description="Last attempt")
    last_error: Optional[str] = Field(default=None, description="Last error")
    etag: Optional[str] = Field(default=None, description="ETag")
    last_etag: Optional[str] = Field(default=None, description="Last ETag")
    request_count: int = Field(default=0, description="Request count")
    discovered_count: int = Field(default=0, description="Discovered count")
    updated_count: int = Field(default=0, description="Updated count")
    failed_count: int = Field(default=0, description="Failed count")
    rate_limit_remaining: Optional[int] = Field(default=None, description="Rate limit remaining")
    rate_limit_reset: Optional[datetime] = Field(default=None, description="Rate limit reset")


class SyncJobSchema(BaseSchema):
    """Schema for a sync job."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    job_id: str = Field(..., description="Job identifier")
    job_type: str = Field(..., description="Job type")
    status: str = Field(default="pending", description="Status")
    application_id: Optional[UUID] = Field(default=None, description="Application identifier")
    repository_id: Optional[UUID] = Field(default=None, description="Repository identifier")
    source_id: Optional[UUID] = Field(default=None, description="Source identifier")
    priority: int = Field(default=0, description="Priority")
    retry_count: int = Field(default=0, description="Retry count")
    max_retries: int = Field(default=3, description="Max retries")
    started_at: Optional[datetime] = Field(default=None, description="Started at")
    completed_at: Optional[datetime] = Field(default=None, description="Completed at")
    duration_ms: Optional[int] = Field(default=None, description="Duration in ms")
    error_message: Optional[str] = Field(default=None, description="Error message")
    error_code: Optional[str] = Field(default=None, description="Error code")
    result: Dict[str, Any] = Field(default_factory=dict, description="Result")
    worker_id: Optional[str] = Field(default=None, description="Worker identifier")
    queue_name: Optional[str] = Field(default=None, description="Queue name")
    is_locked: bool = Field(default=False, description="Is locked")
    locked_at: Optional[datetime] = Field(default=None, description="Locked at")
    locked_by: Optional[str] = Field(default=None, description="Locked by")
