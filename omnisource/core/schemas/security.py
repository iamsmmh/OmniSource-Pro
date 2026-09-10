"""Pydantic schemas for security scans."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field

from omnisource.core.schemas.base import BaseSchema


class SecurityStatusSchema(str, Enum):
    """Security status of an application."""

    UNKNOWN = "unknown"
    PASSED_STATIC_CHECKS = "passed_static_checks"
    FLAGGED = "flagged"
    REVIEW_REQUIRED = "review_required"


class SecurityScanSchema(BaseSchema):
    """Schema for a security scan result."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = Field(default=None, description="Unique identifier")
    application_id: UUID = Field(..., description="Application identifier")
    scan_type: str = Field(..., description="Scan type")
    scanner_version: str | None = Field(default=None, description="Scanner version")
    scan_status: str = Field(..., description="Scan status")
    findings: list[dict[str, Any]] = Field(default_factory=list, description="Findings")
    vulnerabilities: list[dict[str, Any]] = Field(
        default_factory=list, description="Vulnerabilities"
    )
    severity: str | None = Field(default=None, description="Severity")
    confidence: float = Field(default=0.0, description="Confidence (0-1)")
    scanned_at: datetime | None = Field(default=None, description="Scanned at")
    scanned_by: str | None = Field(default=None, description="Scanned by")
    scan_duration_ms: int | None = Field(default=None, description="Scan duration in ms")
