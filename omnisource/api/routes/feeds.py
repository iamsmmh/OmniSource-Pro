"""Legacy and signed feed delivery endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from omnisource.api.dependencies import get_db
from omnisource.config.settings import get_settings
from omnisource.core.repositories.application import ApplicationRepository
from omnisource.core.schemas.omnistore import OmniStoreApp
from omnisource.feeds.schemas import FeedV1
from omnisource.feeds.signing import verify_signed_envelope

router = APIRouter()


async def _legacy_feed(platform: str, session) -> list[OmniStoreApp]:
    """Return the historical array-only feed shape without breaking OmniStore clients."""
    repository = ApplicationRepository(session)
    if platform == "all":
        return await repository.get_all_apps()
    return await repository.get_apps_by_platform(platform)


@router.get("/v1/ios.json", response_model=list[OmniStoreApp], deprecated=True)
async def get_ios_feed(session=Depends(get_db)) -> list[OmniStoreApp]:
    """Legacy iOS feed; use the signed stable channel feed for new clients."""
    return await _legacy_feed("ios", session)


@router.get("/v1/android.json", response_model=list[OmniStoreApp], deprecated=True)
async def get_android_feed(session=Depends(get_db)) -> list[OmniStoreApp]:
    """Legacy Android feed; use the signed stable channel feed for new clients."""
    return await _legacy_feed("android", session)


@router.get("/v1/windows.json", response_model=list[OmniStoreApp], deprecated=True)
async def get_windows_feed(session=Depends(get_db)) -> list[OmniStoreApp]:
    """Legacy Windows feed; use the signed stable channel feed for new clients."""
    return await _legacy_feed("windows", session)


@router.get("/v1/macos.json", response_model=list[OmniStoreApp], deprecated=True)
async def get_macos_feed(session=Depends(get_db)) -> list[OmniStoreApp]:
    """Legacy macOS feed; use the signed stable channel feed for new clients."""
    return await _legacy_feed("macos", session)


@router.get("/v1/linux.json", response_model=list[OmniStoreApp], deprecated=True)
async def get_linux_feed(session=Depends(get_db)) -> list[OmniStoreApp]:
    """Legacy Linux feed; use the signed stable channel feed for new clients."""
    return await _legacy_feed("linux", session)


@router.get("/v1/all.json", response_model=list[OmniStoreApp], deprecated=True)
async def get_all_feed(session=Depends(get_db)) -> list[OmniStoreApp]:
    """Legacy universal feed; use the signed stable channel feed for new clients."""
    return await _legacy_feed("all", session)


@router.get("/v1/{channel}/{platform}.json", response_model=FeedV1)
async def get_signed_feed(channel: str, platform: str) -> JSONResponse:
    """Deliver a published feed only after cryptographic integrity validation."""
    if channel not in {"stable", "beta", "nightly", "experimental"}:
        raise HTTPException(status_code=404, detail="Unknown feed channel")
    if platform not in {"all", "ios", "android", "windows", "macos", "linux"}:
        raise HTTPException(status_code=404, detail="Unknown platform")
    settings = get_settings()
    path = (
        Path(settings.feeds.FEEDS_DIR) / settings.feeds.FEEDS_VERSION / channel / f"{platform}.json"
    )
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Feed has not been published yet")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        feed = FeedV1.model_validate(payload)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Feed is unavailable") from exc
    if not verify_signed_envelope(feed.model_dump(mode="json")):
        raise HTTPException(status_code=503, detail="Feed failed integrity verification")
    return JSONResponse(content=feed.model_dump(mode="json"))
