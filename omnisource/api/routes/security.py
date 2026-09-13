"""Read-only security score, scan evidence, and security-profile API.

* ``GET /api/v1/security/{app_id}`` - scan-derived security/risk scores
* ``GET /api/v1/security/profiles/{app_id}`` - the trust & security profile
  (six verification signals, each worth 20 points, trust_score 0-100)
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from omnisource.api.dependencies import get_db
from omnisource.api.envelope import success
from omnisource.core.models.application import Application
from omnisource.core.models.quarantine import SecurityScan
from omnisource.core.models.security_profile import AppSecurityProfile
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


@router.get("/profiles/{app_id}")
async def app_security_profile(app_id: str, session=Depends(get_db)):
    """Return the application's security/trust profile.

    The profile is derived from persisted evidence (open-source status,
    repository verification, signed builds, hash verification, maintainer and
    organization verification). If no profile exists yet it is computed
    on demand (read-only side effect, committed for durability).
    """
    from omnisource.intelligence.security_profiles import refresh_profile

    result = await session.execute(
        select(Application).where((Application.app_id == app_id) | (Application.slug == app_id))
    )
    app = result.scalars().first()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    profile = await session.scalar(
        select(AppSecurityProfile).where(AppSecurityProfile.application_id == app.id)
    )
    if profile is None:
        profile = await refresh_profile(session, app.id, calculated_by="read-api")
        await session.commit()

    return success(
        data={
            "app_id": app.app_id,
            "verification_status": profile.verification_status.value,
            "trust_score": profile.trust_score,
            "signals": {
                "open_source": {
                    "verified": profile.open_source,
                    "points": 20 if profile.open_source else 0,
                    "label": "Open source repository",
                },
                "github_verified": {
                    "verified": profile.github_verified,
                    "points": 20 if profile.github_verified else 0,
                    "label": "Verified repository",
                },
                "signature_verified": {
                    "verified": profile.signature_verified,
                    "points": 20 if profile.signature_verified else 0,
                    "label": "Signed build",
                },
                "hash_verified": {
                    "verified": profile.hash_verified,
                    "points": 20 if profile.hash_verified else 0,
                    "label": "Hash verified",
                },
                "maintainer_verified": {
                    "verified": profile.maintainer_verified,
                    "points": 20 if profile.maintainer_verified else 0,
                    "label": "Maintainer verified",
                },
            },
            "calculated_at": profile.calculated_at,
            "calculated_by": profile.calculated_by,
            "notes": profile.notes,
        },
        meta={"scoring": "additive, 20 points per verified signal, 0-100"},
    )


@router.get("/{app_id}")
async def app_security(app_id: str, session=Depends(get_db)):
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
    response = SecurityResponse(
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
    return success(data=response.model_dump(mode="json"), meta={"app_id": app_id})
