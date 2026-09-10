"""Sync state and job models."""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.application import Application
from omnisource.core.models.base import Base
from omnisource.core.models.repository import Repository
from omnisource.core.models.source import Source


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
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("sources.id"), index=True)
    repository_id: Mapped[UUID | None] = mapped_column(ForeignKey("repositories.id"), index=True)
    cursor: Mapped[str | None] = mapped_column(String(500))
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    etag: Mapped[str | None] = mapped_column(String(255))
    last_etag: Mapped[str | None] = mapped_column(String(255))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    rate_limit_remaining: Mapped[int | None] = mapped_column(Integer)
    rate_limit_reset: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    source: Mapped[Source | None] = relationship("Source", back_populates="sync_state")
    repository: Mapped[Repository | None] = relationship("Repository", back_populates="sync_state")


class SyncJob(Base):
    """Represents a background sync job."""

    __tablename__ = "sync_jobs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    job_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    job_type: Mapped[SyncJobType] = mapped_column(SQLEnum(SyncJobType), nullable=False, index=True)
    status: Mapped[SyncJobStatus] = mapped_column(
        SQLEnum(SyncJobStatus), default=SyncJobStatus.PENDING, index=True
    )
    application_id: Mapped[UUID | None] = mapped_column(ForeignKey("applications.id"), index=True)
    repository_id: Mapped[UUID | None] = mapped_column(ForeignKey("repositories.id"), index=True)
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("sources.id"), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(String(1000))
    error_code: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    worker_id: Mapped[str | None] = mapped_column(String(255))
    queue_name: Mapped[str | None] = mapped_column(String(100))
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(255))

    # Relationships
    application: Mapped[Application | None] = relationship(
        "Application", back_populates="sync_jobs"
    )
    repository: Mapped[Repository | None] = relationship("Repository")
    source: Mapped[Source | None] = relationship("Source")
