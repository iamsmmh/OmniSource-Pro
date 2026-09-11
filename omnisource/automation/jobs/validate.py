"""Asset validation job."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.core.models.asset import Asset, AssetStatus
from omnisource.core.models.quarantine import SecurityScan
from omnisource.core.models.release import Release, ReleaseAsset
from omnisource.processing.security_engine import SecurityOrchestrator
from omnisource.processing.validation.asset_validator import validate_asset

logger = get_logger(__name__)


async def run_validation(
    session: AsyncSession,
    limit: int = 500,
    **kwargs: Any,
) -> dict[str, Any]:
    """Re-validate assets that are pending, stale, or failed."""
    result = await session.execute(
        select(Asset)
        .where(Asset.status.in_([AssetStatus.PENDING, AssetStatus.STALE, AssetStatus.FAILED]))
        .limit(limit)
    )
    assets = result.scalars().all()

    validated = 0
    scanner = SecurityOrchestrator()
    for asset in assets:
        outcome = validate_asset(
            {
                "download_url": asset.download_url,
                "filename": asset.filename,
                "size_bytes": asset.size_bytes,
                "sha256": asset.sha256,
                "sha512": asset.sha512,
                "package_type": asset.package_type,
            }
        )
        asset.status = AssetStatus(outcome.status)
        asset.validation_status = outcome.status
        asset.validation_message = "; ".join(outcome.errors + outcome.warnings)[:500] or None
        asset.last_validated_at = datetime.now(UTC)

        application_id = await session.scalar(
            select(Release.application_id)
            .join(ReleaseAsset, ReleaseAsset.release_id == Release.id)
            .where(ReleaseAsset.asset_id == asset.id)
            .limit(1)
        )
        if application_id is not None:
            evidence = await scanner.scan_artifact(asset.filename, asset.sha256)
            for item in evidence:
                session.add(
                    SecurityScan(
                        application_id=application_id,
                        scan_type=item.scan_type,
                        scanner_version="v1",
                        scan_status=item.status,
                        findings=item.findings,
                        severity=item.severity,
                        confidence=item.confidence,
                        scanned_by="validation_worker",
                    )
                )
            if any(item.status == "flagged" for item in evidence):
                asset.status = AssetStatus.QUARANTINED
                asset.validation_status = "quarantined"
                asset.validation_message = "Security scanner flagged the artifact"
        validated += 1

    await session.commit()
    logger.info("Validation job completed: %d assets validated", validated)
    return {"validated": validated}
