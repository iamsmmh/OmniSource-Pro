"""Validation result models."""

from datetime import datetime, UTC
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base
from omnisource.core.models.application import Application
from omnisource.core.models.asset import Asset


class ValidationType(str, Enum):
    """Types of validation."""

    URL = "url"
    CHECKSUM = "checksum"
    ASSET = "asset"
    METADATA = "metadata"
    SECURITY = "security"
    LICENSE = "license"
    DEDUPLICATION = "deduplication"


class ValidationStatus(str, Enum):
    """Status of validation."""

    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class ValidationErrorCode(str, Enum):
    """Error codes for validation failures."""

    NETWORK_ERROR = "network_error"
    RATE_LIMIT = "rate_limit"
    INVALID_METADATA = "invalid_metadata"
    INVALID_ASSET = "invalid_asset"
    AUTH_ERROR = "auth_error"
    PARSER_ERROR = "parser_error"
    SECURITY_ERROR = "security_error"
    UNKNOWN_ERROR = "unknown_error"
    HTTP_404 = "http_404"
    HTTP_403 = "http_403"
    HTTP_410 = "http_410"
    TIMEOUT = "timeout"
    INVALID_CONTENT = "invalid_content"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    MALWARE_DETECTED = "malware_detected"
    SSRF_DETECTED = "ssrf_detected"


class ValidationResult(Base):
    """Represents a validation result for an application or asset."""

    __tablename__ = "validation_results"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    application_id: Mapped[Optional[UUID]] = mapped_column(
        foreign_key="applications.id", index=True
    )
    asset_id: Mapped[Optional[UUID]] = mapped_column(
        foreign_key="assets.id", index=True
    )
    validation_type: Mapped[ValidationType] = mapped_column(
        SQLEnum(ValidationType), nullable=False, index=True
    )
    status: Mapped[ValidationStatus] = mapped_column(
        SQLEnum(ValidationStatus), default=ValidationStatus.PENDING, index=True
    )
    error_code: Mapped[Optional[ValidationErrorCode]] = mapped_column(
        SQLEnum(ValidationErrorCode), index=True
    )
    message: Mapped[Optional[str]] = mapped_column(String(500))
    details: Mapped[dict] = mapped_column(String, default={})
    validated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(UTC), nullable=False
    )
    validated_by: Mapped[Optional[str]] = mapped_column(String(100))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_retriable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    application: Mapped[Optional[Application]] = relationship(
        "Application", back_populates="validation_results"
    )
    asset: Mapped[Optional[Asset]] = relationship(
        "Asset"
    )
