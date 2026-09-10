"""Asset validation job."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.core.models.asset import Asset, AssetStatus
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
        validated += 1

    await session.commit()
    logger.info("Validation job completed: %d assets validated", validated)
    return {"validated": validated}
