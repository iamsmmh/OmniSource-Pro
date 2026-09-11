"""Trust score and badge API."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from omnisource.api.dependencies import get_db
from omnisource.core.models.application import Application
from omnisource.core.models.quarantine import SecurityScan
from omnisource.core.models.scores import TrustScore
from omnisource.core.schemas.recommendations import TrustBadge, TrustResponse

router = APIRouter()


def _badges(
    app: Application, score: TrustScore | None, scans: list[SecurityScan]
) -> list[TrustBadge]:
    badges: list[TrustBadge] = []
    normalized = round(score.normalized_score) if score else 0
    factors = score.factors if score and isinstance(score.factors, dict) else {}
    valid_assets = float(factors.get("asset_validation", 0))
    contributors = float(factors.get("contributor_diversity", 0))
    passed_scan = any(scan.scan_status.startswith("passed") for scan in scans)
    flagged = any(
        scan.scan_status == "flagged" or scan.severity in {"high", "critical"} for scan in scans
    )
    if valid_assets >= 0.8 and not flagged:
        badges.append(TrustBadge.VERIFIED)
    if normalized >= 80 and not flagged:
        badges.append(TrustBadge.TRUSTED)
    if contributors >= 0.7:
        badges.append(TrustBadge.COMMUNITY_VERIFIED)
    if passed_scan and not flagged:
        badges.append(TrustBadge.SECURITY_AUDITED)
    if len(app.releases) < 2:
        badges.append(TrustBadge.EXPERIMENTAL)
    if not app.is_active or any(release.status.value == "deprecated" for release in app.releases):
        badges.append(TrustBadge.DEPRECATED)
    return badges


@router.get("/{app_id}", response_model=TrustResponse)
async def app_trust(app_id: str, session=Depends(get_db)) -> TrustResponse:
    """Return the transparent trust factor breakdown and derived badges for an app."""
    result = await session.execute(
        select(Application)
        .where((Application.app_id == app_id) | (Application.slug == app_id))
        .options(
            selectinload(Application.trust_score),
            selectinload(Application.security_scans),
            selectinload(Application.releases),
        )
    )
    app = result.scalars().first()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    score = app.trust_score
    factors = score.factors if score and isinstance(score.factors, dict) else {}
    return TrustResponse(
        app_id=app.app_id,
        score=round(score.normalized_score) if score else None,
        factors={str(key): float(value) for key, value in factors.items()},
        badges=_badges(app, score, app.security_scans),
        calculated_at=score.calculated_at if score else None,
    )
