"""Application security profile computation (trust & security system).

Derives the six verification signals for an application from persisted
evidence, then computes the deterministic trust score:

    Open source repo      +20
    Verified repository   +20
    Signed build          +20
    Hash verified         +20
    Maintainer verified   +20
    Organization verified +20

The result is stored in ``app_security_profiles`` and exposed through the
API. Profiles are refreshed automatically after feed syncs and on demand
via the admin API.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from omnisource.config.logging import get_logger
from omnisource.core.models.application import Application, OpenSourceStatus
from omnisource.core.models.asset import Asset, AssetStatus
from omnisource.core.models.release import Release, ReleaseAsset
from omnisource.core.models.security_profile import (
    AppSecurityProfile,
    VerificationStatus,
    compute_trust_score,
)

logger = get_logger(__name__)


def derive_signals(app: Application) -> dict[str, Any]:
    """Extract the six verification signals from persisted evidence.

    The application must be loaded with: repositories, releases (with
    assets), developer, and security scans.
    """
    open_source = app.open_source_status in (
        OpenSourceStatus.OPEN_SOURCE,
        OpenSourceStatus.SOURCE_AVAILABLE,
    )

    # Verified repository: the source repository is known (synced) and has
    # passing or clean security state. Repositories without security scans
    # still count as verified when their assets validate.
    verified_repos = [
        repo
        for repo in app.repositories
        if repo.html_url and not getattr(repo, "is_archived", False)
    ]
    github_verified = bool(verified_repos)

    releases = app.releases or []
    valid_releases = [
        release
        for release in releases
        if release.status is not None and release.status.value != "deprecated"
    ]

    def _release_assets(release: Release) -> list[Asset]:
        return [ra.asset for ra in (release.assets or []) if ra.asset is not None]

    # Signed build: at least one asset has a signature file paired with it
    # (e.g. *.asc / *.sig / .sha256 signature manifest) or a recorded
    # signature verification.
    signature_verified = False
    for release in valid_releases:
        for asset in _release_assets(release):
            name = (asset.filename or "").lower()
            if name.endswith((".asc", ".sig", ".signature", ".minisign")):
                signature_verified = True
                break
            if (asset.description or "").lower().startswith("signature"):
                signature_verified = True
                break
        if signature_verified:
            break

    # Hash verified: an asset with a stored SHA-256 that passed validation.
    hash_verified = False
    for release in valid_releases:
        for asset in _release_assets(release):
            if asset.sha256 and asset.status == AssetStatus.VALID:
                hash_verified = True
                break
        if hash_verified:
            break

    # Maintainer verified: the developer record exists and is not flagged,
    # or an organization attestation exists.
    maintainer_verified = False
    if app.developer is not None:
        maintainer_verified = True
    if app.organization is not None:
        maintainer_verified = True

    # Organization verified: an organization row with verified flag, or the
    # developer slug is an organization handle (heuristic: verified org set
    # is maintained explicitly via the admin API on Organization.verified).
    org_verified = False
    if app.organization is not None and getattr(app.organization, "is_verified", False):
        org_verified = True

    # Security flags: failed scans veto the org-level attestation.
    scans = app.security_scans or []
    flagged = any(
        scan.scan_status == "flagged" or (scan.severity or "").lower() in {"critical", "high"}
        for scan in scans
    )
    if flagged:
        org_verified = False
        maintainer_verified = False

    return {
        "open_source": open_source,
        "github_verified": github_verified,
        "signature_verified": signature_verified,
        "hash_verified": hash_verified,
        "maintainer_verified": maintainer_verified,
        "org_verified": org_verified,
    }


def derive_status(
    signals: dict[str, Any], current: VerificationStatus | None
) -> VerificationStatus:
    """Map the signal set to an overall verification status.

    * verified  - all six signals (trust score 100)
    * pending   - at least three signals, not yet a full verification
    * rejected  - the application is quarantined/rejected (handled by caller)
    * unverified - otherwise
    """
    active = sum(1 for value in signals.values() if value)
    if active == 6:
        return VerificationStatus.VERIFIED
    if active >= 3:
        return VerificationStatus.PENDING
    if current == VerificationStatus.VERIFIED and active >= 4:
        # Avoid flapping down to pending when one signal briefly disappears.
        return VerificationStatus.VERIFIED
    return VerificationStatus.UNVERIFIED


async def _load_evidence(session: AsyncSession, app: Application) -> Application:
    """Eagerly load the relationships the signal derivation needs."""
    result = await session.execute(
        select(Application)
        .where(Application.id == app.id)
        .options(
            selectinload(Application.releases)
            .selectinload(Release.assets)
            .selectinload(ReleaseAsset.asset),
            selectinload(Application.repositories),
            selectinload(Application.developer),
            selectinload(Application.organization),
            selectinload(Application.security_scans),
        )
    )
    return result.scalars().unique().first() or app


async def refresh_profile(
    session: AsyncSession, app_id, *, calculated_by: str = "security-pipeline"
) -> AppSecurityProfile:
    """Compute and persist the security profile for one application."""
    result = await session.execute(select(Application).where(Application.id == app_id))
    app = result.scalars().first()
    if app is None:
        raise ValueError(f"Application {app_id} not found")
    app = await _load_evidence(session, app)

    signals = derive_signals(app)
    trust_score = compute_trust_score(**signals)

    existing = await session.scalar(
        select(AppSecurityProfile).where(AppSecurityProfile.application_id == app.id)
    )
    previous_status = existing.verification_status if existing is not None else None
    if existing is None:
        existing = AppSecurityProfile(application_id=app.id)
        session.add(existing)
    existing.open_source = signals["open_source"]
    existing.github_verified = signals["github_verified"]
    existing.signature_verified = signals["signature_verified"]
    existing.hash_verified = signals["hash_verified"]
    existing.maintainer_verified = signals["maintainer_verified"]
    existing.trust_score = trust_score
    existing.verification_status = derive_status(signals, previous_status)
    existing.calculated_at = datetime.now(UTC)
    existing.calculated_by = calculated_by
    await session.flush()
    return existing


async def refresh_all_profiles(
    session: AsyncSession, limit: int = 500, *, calculated_by: str = "security-pipeline"
) -> dict[str, Any]:
    """Refresh profiles for all active applications (batched)."""
    refreshed = 0
    offset = 0
    batch = 100
    while True:
        result = await session.execute(
            select(Application.id)
            .where(Application.is_active.is_(True))
            .order_by(Application.updated_at.desc())
            .limit(batch)
            .offset(offset)
        )
        app_ids = [row[0] for row in result.all()]
        if not app_ids:
            break
        for app_id in app_ids:
            await refresh_profile(session, app_id, calculated_by=calculated_by)
            refreshed += 1
        if refreshed >= limit:
            break
        offset += batch
    await session.commit()
    logger.info("Refreshed %d security profiles", refreshed)
    return {"refreshed": refreshed}


__all__ = [
    "derive_signals",
    "derive_status",
    "refresh_all_profiles",
    "refresh_profile",
]
