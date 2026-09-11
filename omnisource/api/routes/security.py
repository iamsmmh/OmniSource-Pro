"""Read-only security score and scan evidence API."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from omnisource.api.dependencies import get_db
from omnisource.core.models.application import Application
from omnisource.core.models.quarantine import SecurityScan
from omnisource.core.schemas.recommendations import SecurityResponse

router = APIRouter()

_SEVERITY_RISK = {"critical": 45, "high": 30, "medium": 15, "moderate": 15, "low": 5}


def _score(scans: list[SecurityScan]) -> tuple[int, int, str, datetime | None]:
    if not scans:
        return 0, 100, "not_scanned", None
    risk = 0
    latest = max((scan.scanned_at for scan in scans), default=None)
    for scan in scans:
        risk += _SEVERITY_RISK.get((scan.severity or "").lower(), 0)
        risk += min(15, len(scan.findings or []) * 3)
        risk += min(20, len(scan.vulnerabilities or []) * 5)
        if scan.scan_status == "flagged":
            risk += 10
    risk = min(100, risk)
    status = "flagged" if risk >= 35 else "passed" if risk == 0 else "review_required"
    return 100 - risk, risk, status, latest


@router.get("/{app_id}", response_model=SecurityResponse)
async def app_security(app_id: str, session=Depends(get_db)) -> SecurityResponse:
    """Return persisted security scan evidence and derived security/risk scores."""
    result = await session.execute(
        select(Application)
        .where((Application.app_id == app_id) | (Application.slug == app_id))
        .options(selectinload(Application.security_scans))
    )
    app = result.scalars().first()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    scans = sorted(app.security_scans, key=lambda scan: scan.scanned_at, reverse=True)
    security_score, risk_score, overall_status, latest = _score(scans)
    return SecurityResponse(
        app_id=app.app_id,
        security_score=security_score,
        risk_score=risk_score,
        status=overall_status,
        latest_scanned_at=latest,
        scans=[
            {
                "type": scan.scan_type,
                "status": scan.scan_status,
                "severity": scan.severity,
                "confidence": scan.confidence,
                "findings": scan.findings,
                "vulnerabilities": scan.vulnerabilities,
                "scanned_at": scan.scanned_at,
                "scanner_version": scan.scanner_version,
            }
            for scan in scans[:20]
        ],
    )
