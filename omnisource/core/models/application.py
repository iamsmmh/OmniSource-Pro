"""Application models for software applications."""

from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base

if TYPE_CHECKING:
    # Resolved by SQLAlchemy relationship() at runtime; imported for type checkers only.
    from omnisource.core.models.architecture import Architecture
    from omnisource.core.models.category import Category
    from omnisource.core.models.developer import Developer
    from omnisource.core.models.icon import Icon
    from omnisource.core.models.license import License
    from omnisource.core.models.organization import Organization
    from omnisource.core.models.platform import Platform
    from omnisource.core.models.popularityscore import PopularityScore
    from omnisource.core.models.qualityscore import QualityScore
    from omnisource.core.models.quarantine import Quarantine
    from omnisource.core.models.release import Release
    from omnisource.core.models.repository import Repository
    from omnisource.core.models.screenshot import Screenshot
    from omnisource.core.models.securityscan import SecurityScan
    from omnisource.core.models.syncjob import SyncJob
    from omnisource.core.models.tag import Tag
    from omnisource.core.models.trustscore import TrustScore
    from omnisource.core.models.validationresult import ValidationResult


class ApplicationStatus(str, Enum):
    """Status of an application."""

    DRAFT = "draft"
    PUBLISHED = "published"
    QUARANTINED = "quarantined"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


class OpenSourceStatus(str, Enum):
    """Open source status of an application."""

    OPEN_SOURCE = "open_source"
    SOURCE_AVAILABLE = "source_available"
    UNKNOWN = "unknown"
    NOT_OPEN_SOURCE = "not_open_source"
    REVIEW_REQUIRED = "review_required"


class ApplicationRelationshipType(str, Enum):
    """Types of relationships between applications."""

    ALTERNATIVE_TO = "alternative_to"
    SIMILAR_TO = "similar_to"
    FORK_OF = "fork_of"
    COMPANION_TO = "companion_to"
    PLATFORM_VARIANT_OF = "platform_variant_of"


class Application(Base):
    """Represents a software application (may span multiple repositories)."""

    __tablename__ = "applications"
    # ``updated_at`` is inherited from Base; the explicit index keeps fresh
    # ``create_all`` schemas identical to the Alembic-managed production schema
    # (see migration 0008).
    __table_args__ = (Index("ix_applications_updated_at", "updated_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    app_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Stable platform bundle/package identifier (e.g. com.example.app,
    # org.project.tool). Primary deduplication key across sources.
    bundle_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Primary category; the many-to-many ``categories`` relationship remains
    # authoritative for secondary categories.
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Cumulative download counter, incremented by the analytics ingestion API
    # and used by the trending/most-downloaded materialized views.
    download_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False, index=True
    )
    short_description: Mapped[str | None] = mapped_column(String(500))
    long_description: Mapped[str | None] = mapped_column(Text)
    homepage: Mapped[str | None] = mapped_column(String(500))
    documentation_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[ApplicationStatus] = mapped_column(
        SQLEnum(ApplicationStatus), default=ApplicationStatus.DRAFT, index=True
    )
    open_source_status: Mapped[OpenSourceStatus] = mapped_column(
        SQLEnum(OpenSourceStatus), default=OpenSourceStatus.UNKNOWN, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    developer_id: Mapped[UUID | None] = mapped_column(ForeignKey("developers.id"), index=True)
    organization_id: Mapped[UUID | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    license_id: Mapped[UUID | None] = mapped_column(ForeignKey("licenses.id"), index=True)

    # Relationships
    repositories: Mapped[list["Repository"]] = relationship(
        "Repository", back_populates="applications", secondary="application_repositories"
    )
    developer: Mapped[Optional["Developer"]] = relationship(
        "Developer", back_populates="applications"
    )
    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization", back_populates="applications"
    )
    license: Mapped[Optional["License"]] = relationship("License", back_populates="applications")
    platforms: Mapped[list["Platform"]] = relationship(
        "Platform", secondary="application_platforms", back_populates="applications"
    )
    architectures: Mapped[list["Architecture"]] = relationship(
        "Architecture", secondary="application_architectures", back_populates="applications"
    )
    categories: Mapped[list["Category"]] = relationship(
        "Category", secondary="application_categories", back_populates="applications"
    )
    tags: Mapped[list["Tag"]] = relationship(
        "Tag", secondary="application_tags", back_populates="applications"
    )
    releases: Mapped[list["Release"]] = relationship(
        "Release", back_populates="application", cascade="all, delete-orphan"
    )
    screenshots: Mapped[list["Screenshot"]] = relationship(
        "Screenshot", back_populates="application", cascade="all, delete-orphan"
    )
    icons: Mapped[list["Icon"]] = relationship(
        "Icon", back_populates="application", cascade="all, delete-orphan"
    )
    trust_score: Mapped[Optional["TrustScore"]] = relationship(
        "TrustScore", back_populates="application", uselist=False, cascade="all, delete-orphan"
    )
    quality_score: Mapped[Optional["QualityScore"]] = relationship(
        "QualityScore", back_populates="application", uselist=False, cascade="all, delete-orphan"
    )
    popularity_score: Mapped[Optional["PopularityScore"]] = relationship(
        "PopularityScore", back_populates="application", uselist=False, cascade="all, delete-orphan"
    )
    security_scans: Mapped[list["SecurityScan"]] = relationship(
        "SecurityScan", back_populates="application", cascade="all, delete-orphan"
    )
    quarantine: Mapped[Optional["Quarantine"]] = relationship(
        "Quarantine", back_populates="application", uselist=False, cascade="all, delete-orphan"
    )
    validation_results: Mapped[list["ValidationResult"]] = relationship(
        "ValidationResult", back_populates="application", cascade="all, delete-orphan"
    )
    relationships_from: Mapped[list["ApplicationRelationship"]] = relationship(
        "ApplicationRelationship",
        foreign_keys="ApplicationRelationship.from_app_id",
        back_populates="from_app",
        cascade="all, delete-orphan",
    )
    relationships_to: Mapped[list["ApplicationRelationship"]] = relationship(
        "ApplicationRelationship",
        foreign_keys="ApplicationRelationship.to_app_id",
        back_populates="to_app",
        cascade="all, delete-orphan",
    )
    sync_jobs: Mapped[list["SyncJob"]] = relationship(
        "SyncJob", back_populates="application", cascade="all"
    )


class ApplicationRelationship(Base):
    """Represents a relationship between two applications."""

    __tablename__ = "application_relationships"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    from_app_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), nullable=False, index=True
    )
    to_app_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), nullable=False, index=True
    )
    relationship_type: Mapped[ApplicationRelationshipType] = mapped_column(
        SQLEnum(ApplicationRelationshipType), nullable=False, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str | None] = mapped_column(String(100))
    created_by: Mapped[str | None] = mapped_column(String(100))

    # Relationships
    from_app: Mapped[Application] = relationship(
        "Application", foreign_keys=[from_app_id], back_populates="relationships_from"
    )
    to_app: Mapped[Application] = relationship(
        "Application", foreign_keys=[to_app_id], back_populates="relationships_to"
    )


# Association tables for many-to-many relationships
application_repositories = Table(
    "application_repositories",
    Base.metadata,
    Column("application_id", ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True),
    Column("repository_id", ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True),
    Column("is_primary", Boolean, default=False),
    Column("confidence", Float, default=1.0),
)

application_platforms = Table(
    "application_platforms",
    Base.metadata,
    Column("application_id", ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True),
    Column("platform_id", ForeignKey("platforms.id", ondelete="CASCADE"), primary_key=True),
)

application_architectures = Table(
    "application_architectures",
    Base.metadata,
    Column("application_id", ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True),
    Column("architecture_id", ForeignKey("architectures.id", ondelete="CASCADE"), primary_key=True),
)

application_categories = Table(
    "application_categories",
    Base.metadata,
    Column("application_id", ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)

application_tags = Table(
    "application_tags",
    Base.metadata,
    Column("application_id", ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)
