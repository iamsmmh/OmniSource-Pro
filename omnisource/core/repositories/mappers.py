"""Mappers converting ORM entities into OmniStore-compatible schemas."""

from datetime import datetime
from typing import Any, cast

from omnisource.core.models.application import Application
from omnisource.core.models.asset import AssetStatus
from omnisource.core.schemas.omnistore import (
    OmniStoreApp,
    OmniStoreArchitecture,
    OmniStoreAsset,
    OmniStoreAssetStatus,
    OmniStoreDeveloper,
    OmniStorePlatform,
    OmniStoreRelease,
    OmniStoreScores,
)

_ASSET_STATUS_MAP = {
    AssetStatus.VALID: OmniStoreAssetStatus.VALID,
    AssetStatus.INVALID: OmniStoreAssetStatus.INVALID,
    AssetStatus.QUARANTINED: OmniStoreAssetStatus.QUARANTINED,
    AssetStatus.REVIEW_REQUIRED: OmniStoreAssetStatus.REVIEW_REQUIRED,
    AssetStatus.UNKNOWN: OmniStoreAssetStatus.UNKNOWN,
    AssetStatus.PENDING: OmniStoreAssetStatus.UNKNOWN,
    AssetStatus.STALE: OmniStoreAssetStatus.INVALID,
    AssetStatus.FAILED: OmniStoreAssetStatus.INVALID,
}


def _omnistore_asset_status(asset) -> OmniStoreAssetStatus:
    raw = getattr(asset, "status", None)
    if isinstance(raw, AssetStatus):
        return _ASSET_STATUS_MAP.get(raw, OmniStoreAssetStatus.UNKNOWN)
    try:
        return _ASSET_STATUS_MAP.get(AssetStatus(str(raw)), OmniStoreAssetStatus.UNKNOWN)
    except (TypeError, ValueError):
        return OmniStoreAssetStatus.UNKNOWN


def _iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _to_omnistore_developer(app: Application) -> OmniStoreDeveloper | None:
    developer = getattr(app, "developer", None)
    if developer is None:
        organization = getattr(app, "organization", None)
        if organization is None:
            return None
        return OmniStoreDeveloper(
            id=organization.slug or organization.organization_id,
            slug=organization.slug,
            name=organization.display_name or organization.name,
            url=organization.url,
        )
    return OmniStoreDeveloper(
        id=developer.slug or developer.developer_id,
        slug=developer.slug,
        name=developer.display_name or developer.name,
        url=developer.url,
    )


def _to_omnistore_scores(app: Application) -> OmniStoreScores | None:
    trust = getattr(app, "trust_score", None)
    quality = getattr(app, "quality_score", None)
    popularity = getattr(app, "popularity_score", None)

    if not (trust or quality or popularity):
        return None

    def _factors(score) -> list[str] | None:
        factors = getattr(score, "factors", None)
        if not factors:
            return None
        if isinstance(factors, dict):
            return sorted(str(k) for k in factors.keys())
        return None

    return OmniStoreScores(
        trust=_norm(trust) if trust else None,
        quality=_norm(quality) if quality else None,
        popularity=_norm(popularity) if popularity else None,
        trust_factors=_factors(trust) if trust else None,
        quality_factors=_factors(quality) if quality else None,
    )


def _norm(score) -> int | None:
    value = getattr(score, "normalized_score", None)
    if value is None:
        value = getattr(score, "score", None)
    if value is None:
        return None
    try:
        return round(float(value))
    except (TypeError, ValueError):
        return None


def _to_omnistore_assets(release) -> list[OmniStoreAsset]:
    assets: list[OmniStoreAsset] = []
    for release_asset in getattr(release, "assets", []) or []:
        asset = getattr(release_asset, "asset", None)
        if asset is None:
            continue
        assets.append(
            OmniStoreAsset(
                id=asset.asset_id,
                platform=OmniStorePlatform(asset.detected_platform or "linux"),
                architecture=OmniStoreArchitecture(asset.detected_architecture or "any"),
                package_type=asset.package_type or asset.file_type or "binary",
                version=asset.version or release.version,
                url=asset.browser_download_url or asset.download_url,
                size_bytes=asset.size_bytes,
                sha256=asset.sha256,
                source=asset.source.value if hasattr(asset.source, "value") else str(asset.source),
                status=_omnistore_asset_status(asset),
            )
        )
    return assets


def _to_omnistore_release(release) -> OmniStoreRelease:
    return OmniStoreRelease(
        version=release.version,
        released_at=_iso(getattr(release, "published_at", None)),
        notes=getattr(release, "body", None),
        assets=_to_omnistore_assets(release),
    )


def to_omnistore_app(app: Application) -> OmniStoreApp:
    """Convert an Application ORM object into an OmniStoreApp schema."""
    releases = sorted(
        (r for r in (getattr(app, "releases", []) or [])),
        key=lambda r: r.published_at or datetime.min,
        reverse=True,
    )
    latest_release = _to_omnistore_release(releases[0]) if releases else None

    categories = [c.slug for c in (getattr(app, "categories", []) or [])]
    tags = [t.slug for t in (getattr(app, "tags", []) or [])]
    platforms = [p.platform_type for p in (getattr(app, "platforms", []) or [])]

    repositories = getattr(app, "repositories", []) or []
    repository_url = repositories[0].html_url if repositories else None

    icons = getattr(app, "icons", []) or []
    icon_url = None
    for icon in icons:
        if getattr(icon, "is_primary", False):
            icon_url = icon.url
            break
    if icon_url is None and icons:
        icon_url = icons[0].url

    screenshots = [s.url for s in (getattr(app, "screenshots", []) or [])]

    license_obj = getattr(app, "license", None)
    license_spdx = license_obj.spdx_id if license_obj else None

    open_source_status = getattr(app, "open_source_status", None)
    open_source = True
    if open_source_status is not None:
        open_source = getattr(open_source_status, "value", str(open_source_status)) in (
            "open_source",
            "source_available",
        )

    return OmniStoreApp(
        id=app.slug or app.app_id,
        slug=app.slug,
        name=app.name,
        short_description=app.short_description,
        description=app.long_description,
        features=None,
        developer=_to_omnistore_developer(app),
        categories=categories,
        tags=tags,
        platforms=platforms,
        license=license_spdx,
        homepage=cast(Any, app.homepage),
        repository=cast(Any, repository_url),
        documentation=cast(Any, app.documentation_url),
        icon=icon_url,
        screenshots=screenshots,
        scores=_to_omnistore_scores(app),
        latest_release=latest_release,
        releases=[_to_omnistore_release(r) for r in releases],
        alternatives=[],
        similar=[],
        source_name=None,
        source_status=None,
        updated_at=_iso(getattr(app, "updated_at", None)),
        created_at=_iso(getattr(app, "created_at", None)),
        open_source=open_source,
        active_development=app.is_active,
    )
