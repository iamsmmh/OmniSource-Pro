"""Pydantic schemas for trust, quality, and popularity scores."""

from datetime import datetime
from typing import Dict, Optional
from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class TrustScoreSchema(BaseSchema):
    """Schema for a trust score."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    application_id: UUID = Field(..., description="Application identifier")
    score: float = Field(default=0.0, description="Raw score")
    normalized_score: float = Field(default=0.0, description="Normalized score (0-100)")
    factors: Dict[str, float] = Field(default_factory=dict, description="Score factors")
    calculated_at: Optional[datetime] = Field(default=None, description="Calculated at")
    calculated_by: Optional[str] = Field(default=None, description="Calculated by")


class QualityScoreSchema(BaseSchema):
    """Schema for a quality score."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    application_id: UUID = Field(..., description="Application identifier")
    score: float = Field(default=0.0, description="Raw score")
    normalized_score: float = Field(default=0.0, description="Normalized score (0-100)")
    factors: Dict[str, float] = Field(default_factory=dict, description="Score factors")
    calculated_at: Optional[datetime] = Field(default=None, description="Calculated at")
    calculated_by: Optional[str] = Field(default=None, description="Calculated by")


class PopularityScoreSchema(BaseSchema):
    """Schema for a popularity score."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    application_id: UUID = Field(..., description="Application identifier")
    score: float = Field(default=0.0, description="Raw score")
    normalized_score: float = Field(default=0.0, description="Normalized score (0-100)")
    factors: Dict[str, float] = Field(default_factory=dict, description="Score factors")
    calculated_at: Optional[datetime] = Field(default=None, description="Calculated at")
    calculated_by: Optional[str] = Field(default=None, description="Calculated by")
    github_stars: int = Field(default=0, description="GitHub stars")
    github_forks: int = Field(default=0, description="GitHub forks")
    release_downloads: int = Field(default=0, description="Release downloads")
    contributors: int = Field(default=0, description="Contributors")
    omnistore_interactions: int = Field(default=0, description="OmniStore interactions")
