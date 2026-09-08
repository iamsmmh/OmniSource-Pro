"""Quarantine and security models."""

from datetime import datetime, UTC
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, JSON, Boolean, DateTime, Enum as SQLEnum, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base
from omnisource.core.models.application import Application
from omnisource.core.models.asset import Asset


class QuarantineReason(str, Enum):
    """Reasons for quarantining an application or asset."""

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


class QuarantineStatus(str, Enum):
    """Status of quarantined items."""

    QUARANTINED = "quarantined"
    REVIEW_PENDING = "review_pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Quarantine(Base):
    """Represents a quarantined application or asset."""

    __tablename__ = "quarantines"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    application_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    asset_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("assets.id"), index=True
    )
    reason: Mapped[QuarantineReason] = mapped_column(
        SQLEnum(QuarantineReason), nullable=False, index=True
    )
    status: Mapped[QuarantineStatus] = mapped_column(
        SQLEnum(QuarantineStatus), default=QuarantineStatus.QUARANTINED, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    quarantined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(UTC), nullable=False
    )
    quarantined_by: Mapped[Optional[str]] = mapped_column(String(100))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100))
    review_notes: Mapped[Optional[str]] = mapped_column(Text)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    application: Mapped[Optional[Application]] = relationship(
        "Application", back_populates="quarantine"
    )
    asset: Mapped[Optional[Asset]] = relationship(
        "Asset"
    )


class SecurityScan(Base):
    """Represents a security scan result for an application."""

    __tablename__ = "security_scans"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), nullable=False, index=True
    )
    scan_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    scanner_version: Mapped[Optional[str]] = mapped_column(String(50))
    scan_status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    findings: Mapped[list[dict]] = mapped_column(JSON, default=list)
    vulnerabilities: Mapped[list[dict]] = mapped_column(JSON, default=list)
    severity: Mapped[Optional[str]] = mapped_column(String(50))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(UTC), nullable=False
    )
    scanned_by: Mapped[Optional[str]] = mapped_column(String(100))
    scan_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # Relationships
    application: Mapped[Application] = relationship(
        "Application", back_populates="security_scans"
    )


class SecurityStatus(str, Enum):
    """Security status of an application."""

    UNKNOWN = "unknown"
    PASSED_STATIC_CHECKS = "passed_static_checks"
    FLAGGED = "flagged"
    REVIEW_REQUIRED = "review_required"
