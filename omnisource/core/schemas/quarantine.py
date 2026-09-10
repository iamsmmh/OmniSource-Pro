"""Pydantic schemas for quarantined items."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class QuarantineReasonSchema(str, Enum):
    """Reasons for quarantining an item."""

    SUSPICIOUS_RELEASE = "suspicious_release"
    UNEXPECTED_BINARY_REPLACEMENT = "unexpected_binary_replacement"
    CHECKSUM_CHANGED = "checksum_changed"
    MAINTAINER_ANOMALY = "maintainer_anomaly"
    SECURITY_SIGNAL = "security_signal"
    MALWARE_DETECTED = "malware_detected"
    LICENSE_VIOLATION = "license_violation"
    POLICY_VIOLATION = "policy_violation"
    MANUAL_REVIEW = "manual_review"
    FALSE_POSITIVE = "false_positive"


class QuarantineStatusSchema(str, Enum):
    """Status of quarantined items."""

    QUARANTINED = "quarantined"
    REVIEW_PENDING = "review_pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class QuarantineSchema(BaseSchema):
    """Schema for a quarantined application or asset."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: UUID | None = Field(default=None, description="Unique identifier")
    application_id: UUID | None = Field(default=None, description="Application identifier")
    asset_id: UUID | None = Field(default=None, description="Asset identifier")
    reason: str = Field(..., description="Reason")
    status: str = Field(default="quarantined", description="Status")
    description: str | None = Field(default=None, description="Description")
    details: dict[str, Any] = Field(default_factory=dict, description="Details")
    quarantined_at: datetime | None = Field(default=None, description="Quarantined at")
    quarantined_by: str | None = Field(default=None, description="Quarantined by")
    reviewed_at: datetime | None = Field(default=None, description="Reviewed at")
    reviewed_by: str | None = Field(default=None, description="Reviewed by")
    review_notes: str | None = Field(default=None, description="Review notes")
    expires_at: datetime | None = Field(default=None, description="Expires at")
    is_active: bool = Field(default=True, description="Is active")
