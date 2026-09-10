"""Repository models for software repositories."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base

if TYPE_CHECKING:
    # Resolved by SQLAlchemy relationship() at runtime; imported for type checkers only.
    from omnisource.core.models.application import Application
    from omnisource.core.models.release import Release
    from omnisource.core.models.syncstate import SyncState
from omnisource.core.models.source import Source


class RepositoryStatus(str, Enum):
    """Status of a repository."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    MIRROR = "mirror"
    EMPTY = "empty"
    UNKNOWN = "unknown"


class RepositoryVisibility(str, Enum):
    """Visibility of a repository."""

    PUBLIC = "public"
    PRIVATE = "private"
    INTERNAL = "internal"


class Repository(Base):
    """Represents a software repository from an external source."""

    __tablename__ = "repositories"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    homepage: Mapped[str | None] = mapped_column(String(500))
    html_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[RepositoryStatus] = mapped_column(
        SQLEnum(RepositoryStatus), default=RepositoryStatus.UNKNOWN, index=True
    )
    visibility: Mapped[RepositoryVisibility] = mapped_column(
        SQLEnum(RepositoryVisibility), default=RepositoryVisibility.PUBLIC, index=True
    )
    is_fork: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stars: Mapped[int] = mapped_column(BigInteger, default=0)
    forks: Mapped[int] = mapped_column(BigInteger, default=0)
    open_issues: Mapped[int] = mapped_column(Integer, default=0)
    size_kb: Mapped[int] = mapped_column(BigInteger, default=0)
    language: Mapped[str | None] = mapped_column(String(50))
    default_branch: Mapped[str | None] = mapped_column(String(100))
    created_at_external: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at_external: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    source: Mapped[Source] = relationship("Source", back_populates="repositories")
    metadata_obj: Mapped[Optional["RepositoryMetadata"]] = relationship(
        "RepositoryMetadata",
        back_populates="repository",
        uselist=False,
        cascade="all, delete-orphan",
    )
    applications: Mapped[list["Application"]] = relationship(
        "Application",
        secondary="application_repositories",
        back_populates="repositories",
    )
    releases: Mapped[list["Release"]] = relationship(
        "Release", back_populates="repository", cascade="all, delete-orphan"
    )
    sync_state: Mapped[list["SyncState"]] = relationship(
        "SyncState", back_populates="repository", cascade="all, delete-orphan"
    )


class RepositoryMetadata(Base):
    """Extended metadata for a repository."""

    __tablename__ = "repository_metadata"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("repositories.id"), nullable=False, unique=True, index=True
    )
    readme: Mapped[str | None] = mapped_column(Text)
    readme_html: Mapped[str | None] = mapped_column(Text)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    license_spdx: Mapped[str | None] = mapped_column(String(100))
    has_wiki: Mapped[bool] = mapped_column(Boolean, default=False)
    has_issues: Mapped[bool] = mapped_column(Boolean, default=False)
    has_discussions: Mapped[bool] = mapped_column(Boolean, default=False)
    has_projects: Mapped[bool] = mapped_column(Boolean, default=False)
    has_downloads: Mapped[bool] = mapped_column(Boolean, default=False)
    contributors_count: Mapped[int] = mapped_column(Integer, default=0)
    commit_count: Mapped[int] = mapped_column(BigInteger, default=0)
    last_commit_sha: Mapped[str | None] = mapped_column(String(100))
    last_commit_message: Mapped[str | None] = mapped_column(String(500))
    last_commit_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    repository: Mapped[Repository] = relationship("Repository", back_populates="metadata_obj")
