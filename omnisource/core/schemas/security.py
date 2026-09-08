"""Pydantic schemas for security scans."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
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

    id: Optional[UUID] = Field(default=None, description="Unique identifier")
    application_id: UUID = Field(..., description="Application identifier")
    scan_type: str = Field(..., description="Scan type")
    scanner_version: Optional[str] = Field(default=None, description="Scanner version")
    scan_status: str = Field(..., description="Scan status")
    findings: List[Dict[str, Any]] = Field(default_factory=list, description="Findings")
    vulnerabilities: List[Dict[str, Any]] = Field(default_factory=list, description="Vulnerabilities")
    severity: Optional[str] = Field(default=None, description="Severity")
    confidence: float = Field(default=0.0, description="Confidence (0-1)")
    scanned_at: Optional[datetime] = Field(default=None, description="Scanned at")
    scanned_by: Optional[str] = Field(default=None, description="Scanned by")
    scan_duration_ms: Optional[int] = Field(default=None, description="Scan duration in ms")
