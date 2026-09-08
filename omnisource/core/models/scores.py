"""Score models for trust, quality, and popularity."""

from datetime import datetime, UTC
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base
from omnisource.core.models.application import Application


class ScoreFactor(Base):
    """Base class for score factors."""

    __abstract__ = True

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    application_id: Mapped[UUID] = mapped_column(
        foreign_key="applications.id", nullable=False, unique=True, index=True
    )
    score: Mapped[float] = mapped_column(Float, default=0.0)
    normalized_score: Mapped[float] = mapped_column(Float, default=0.0)
    factors: Mapped[dict] = mapped_column(String, default={})
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(UTC), nullable=False
    )
    calculated_by: Mapped[Optional[str]] = mapped_column(String(100))


class TrustScore(ScoreFactor):
    """Trust score for an application."""

    __tablename__ = "trust_scores"

    # Trust score factors
    repository_activity_weight: Mapped[float] = mapped_column(Float, default=0.15)
    release_consistency_weight: Mapped[float] = mapped_column(Float, default=0.15)
    license_clarity_weight: Mapped[float] = mapped_column(Float, default=0.10)
    contributor_diversity_weight: Mapped[float] = mapped_column(Float, default=0.10)
    issue_activity_weight: Mapped[float] = mapped_column(Float, default=0.05)
    documentation_weight: Mapped[float] = mapped_column(Float, default=0.05)
    asset_validation_weight: Mapped[float] = mapped_column(Float, default=0.15)
    security_signals_weight: Mapped[float] = mapped_column(Float, default=0.20)
    metadata_quality_weight: Mapped[float] = mapped_column(Float, default=0.05)

    # Relationships
    application: Mapped[Application] = relationship(
        "Application", back_populates="trust_score"
    )


class QualityScore(ScoreFactor):
    """Quality score for an application."""

    __tablename__ = "quality_scores"

    # Quality score factors
    documentation_weight: Mapped[float] = mapped_column(Float, default=0.15)
    activity_weight: Mapped[float] = mapped_column(Float, default=0.15)
    release_frequency_weight: Mapped[float] = mapped_column(Float, default=0.15)
    platform_coverage_weight: Mapped[float] = mapped_column(Float, default=0.15)
    metadata_completeness_weight: Mapped[float] = mapped_column(Float, default=0.15)
    community_activity_weight: Mapped[float] = mapped_column(Float, default=0.15)
    maintenance_status_weight: Mapped[float] = mapped_column(Float, default=0.10)

    # Relationships
    application: Mapped[Application] = relationship(
        "Application", back_populates="quality_score"
    )


class PopularityScore(ScoreFactor):
    """Popularity score for an application."""

    __tablename__ = "popularity_scores"

    # Raw metrics
    github_stars: Mapped[int] = mapped_column(Integer, default=0)
    github_forks: Mapped[int] = mapped_column(Integer, default=0)
    release_downloads: Mapped[int] = mapped_column(Integer, default=0)
    contributors: Mapped[int] = mapped_column(Integer, default=0)
    omnistore_interactions: Mapped[int] = mapped_column(Integer, default=0)

    # Popularity score factors
    stars_weight: Mapped[float] = mapped_column(Float, default=0.25)
    forks_weight: Mapped[float] = mapped_column(Float, default=0.20)
    downloads_weight: Mapped[float] = mapped_column(Float, default=0.20)
    contributors_weight: Mapped[float] = mapped_column(Float, default=0.15)
    activity_weight: Mapped[float] = mapped_column(Float, default=0.10)
    omnistore_weight: Mapped[float] = mapped_column(Float, default=0.10)

    # Relationships
    application: Mapped[Application] = relationship(
        "Application", back_populates="popularity_score"
    )
