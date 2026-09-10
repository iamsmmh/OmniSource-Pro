"""Source models for external software sources."""

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base

if TYPE_CHECKING:
    # Resolved by SQLAlchemy relationship() at runtime; imported for type checkers only.
    from omnisource.core.models.repository import Repository
    from omnisource.core.models.sync import SyncState


class SourceType(str, Enum):
    """Types of external sources."""

    GITHUB = "github"
    GITLAB = "gitlab"
    CODEBERG = "codeberg"
    FORGEJO = "forgejo"
    FDROID = "fdroid"
    FLATHUB = "flathub"
    WINGET = "winget"
    HOMEBREW = "homebrew"
    OTHER = "other"


class SourceHealthStatus(str, Enum):
    """Health status of a source."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class Source(Base):
    """Represents an external software source (e.g., GitHub, GitLab)."""

    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    source_type: Mapped[SourceType] = mapped_column(SQLEnum(SourceType), nullable=False, index=True)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    health: Mapped[list["SourceHealth"]] = relationship(
        "SourceHealth", back_populates="source", cascade="all, delete-orphan"
    )
    repositories: Mapped[list["Repository"]] = relationship(
        "Repository", back_populates="source", cascade="all, delete-orphan"
    )
    sync_state: Mapped[list["SyncState"]] = relationship(
        "SyncState", back_populates="source", cascade="all, delete-orphan"
    )


class SourceHealth(Base):
    """Tracks the health status of a source over time."""

    __tablename__ = "source_health"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    status: Mapped[SourceHealthStatus] = mapped_column(
        SQLEnum(SourceHealthStatus), nullable=False, index=True
    )
    latency_ms: Mapped[float | None] = mapped_column(Float)
    error_rate: Mapped[float] = mapped_column(Float, default=0.0)
    last_check_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(UTC), nullable=False
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    source: Mapped[Source] = relationship("Source", back_populates="health")
