"""Recommendation and trust/security response contracts."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from omnisource.core.schemas.omnistore import OmniStoreApp


class RecommendationKind(str, Enum):
    SIMILAR = "similar"
    ALTERNATIVE = "alternative"
    COLLABORATIVE = "collaborative"
    CATEGORY = "category"
    DEVELOPER = "developer"
    TRENDING = "trending"
    POPULAR = "popular"
    NEW = "new"


class RecommendationItem(BaseModel):
    """An application recommendation with transparent provenance."""

    app: OmniStoreApp
    score: float = Field(ge=0, le=1)
    kind: RecommendationKind
    reasons: list[str] = Field(default_factory=list)


class RecommendationResponse(BaseModel):
    """A stable recommendation response shared by web and mobile clients."""

    subject_app_id: str | None = None
    algorithm_version: str = "v1"
    generated_at: datetime
    items: list[RecommendationItem] = Field(default_factory=list)


class TrustBadge(str, Enum):
    VERIFIED = "verified"
    TRUSTED = "trusted"
    COMMUNITY_VERIFIED = "community_verified"
    SECURITY_AUDITED = "security_audited"
    EXPERIMENTAL = "experimental"
    DEPRECATED = "deprecated"


class TrustResponse(BaseModel):
    """Trust score and auditable factor/badge output."""

    app_id: str
    score: int | None = Field(default=None, ge=0, le=100)
    factors: dict[str, float] = Field(default_factory=dict)
    badges: list[TrustBadge] = Field(default_factory=list)
    calculated_at: datetime | None = None


class SecurityResponse(BaseModel):
    """Aggregate security status for an app without exposing sensitive payloads."""

    app_id: str
    security_score: int = Field(ge=0, le=100)
    risk_score: int = Field(ge=0, le=100)
    status: str
    latest_scanned_at: datetime | None = None
    scans: list[dict[str, Any]] = Field(default_factory=list)
