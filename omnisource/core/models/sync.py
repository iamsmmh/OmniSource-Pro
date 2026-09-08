"""Sync state and job models."""

from datetime import datetime, UTC
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, JSON, Boolean, DateTime, Enum as SQLEnum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base
from omnisource.core.models.source import Source
from omnisource.core.models.repository import Repository
from omnisource.core.models.application import Application


class SyncJobType(str, Enum):
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


class SyncJobStatus(str, Enum):
    """Status of a sync job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class SyncState(Base):
    """Tracks the synchronization state for sources and repositories."""

    __tablename__ = "sync_states"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    source_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("sources.id"), index=True
    )
    repository_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("repositories.id"), index=True
    )
    cursor: Mapped[Optional[str]] = mapped_column(String(500))
    last_success: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_attempt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(String(500))
    etag: Mapped[Optional[str]] = mapped_column(String(255))
    last_etag: Mapped[Optional[str]] = mapped_column(String(255))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    rate_limit_remaining: Mapped[Optional[int]] = mapped_column(Integer)
    rate_limit_reset: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    source: Mapped[Optional[Source]] = relationship(
        "Source", back_populates="sync_state"
    )
    repository: Mapped[Optional[Repository]] = relationship(
        "Repository", back_populates="sync_state"
    )


class SyncJob(Base):
    """Represents a background sync job."""

    __tablename__ = "sync_jobs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    job_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    job_type: Mapped[SyncJobType] = mapped_column(
        SQLEnum(SyncJobType), nullable=False, index=True
    )
    status: Mapped[SyncJobStatus] = mapped_column(
        SQLEnum(SyncJobStatus), default=SyncJobStatus.PENDING, index=True
    )
    application_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    repository_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("repositories.id"), index=True
    )
    source_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("sources.id"), index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_message: Mapped[Optional[str]] = mapped_column(String(1000))
    error_code: Mapped[Optional[str]] = mapped_column(String(100))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    worker_id: Mapped[Optional[str]] = mapped_column(String(255))
    queue_name: Mapped[Optional[str]] = mapped_column(String(100))
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[Optional[str]] = mapped_column(String(255))

    # Relationships
    application: Mapped[Optional[Application]] = relationship(
        "Application", back_populates="sync_jobs"
    )
    repository: Mapped[Optional[Repository]] = relationship(
        "Repository"
    )
    source: Mapped[Optional[Source]] = relationship(
        "Source"
    )
