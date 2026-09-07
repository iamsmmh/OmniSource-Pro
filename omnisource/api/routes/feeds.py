"""
Feed API routes for OmniSource.

Provides static JSON feeds for OmniStore and other clients.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse

from omnisource.config.settings import get_settings
from omnisource.config.logging import get_logger
from omnisource.core.schemas.omnistore import OmniStoreApp
from omnisource.core.repositories.application import ApplicationRepository
from omnisource.core.database.session import get_session

logger = get_logger(__name__)

router = APIRouter()


@router.get("/v1/ios.json")
async def get_ios_feed(
    session=Depends(get_session),
) -> List[OmniStoreApp]:
    """Get iOS feed."""
    try:
        repo = ApplicationRepository(session)
        apps = await repo.get_apps_by_platform("ios")
        return apps
    except Exception as e:
        logger.error(f"Failed to get iOS feed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/android.json")
async def get_android_feed(
    session=Depends(get_session),
) -> List[OmniStoreApp]:
    """Get Android feed."""
    try:
        repo = ApplicationRepository(session)
        apps = await repo.get_apps_by_platform("android")
        return apps
    except Exception as e:
        logger.error(f"Failed to get Android feed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/windows.json")
async def get_windows_feed(
    session=Depends(get_session),
) -> List[OmniStoreApp]:
    """Get Windows feed."""
    try:
        repo = ApplicationRepository(session)
        apps = await repo.get_apps_by_platform("windows")
        return apps
    except Exception as e:
        logger.error(f"Failed to get Windows feed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/macos.json")
async def get_macos_feed(
    session=Depends(get_session),
) -> List[OmniStoreApp]:
    """Get macOS feed."""
    try:
        repo = ApplicationRepository(session)
        apps = await repo.get_apps_by_platform("macos")
        return apps
    except Exception as e:
        logger.error(f"Failed to get macOS feed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/linux.json")
async def get_linux_feed(
    session=Depends(get_session),
) -> List[OmniStoreApp]:
    """Get Linux feed."""
    try:
        repo = ApplicationRepository(session)
        apps = await repo.get_apps_by_platform("linux")
        return apps
    except Exception as e:
        logger.error(f"Failed to get Linux feed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/all.json")
async def get_all_feed(
    session=Depends(get_session),
) -> List[OmniStoreApp]:
    """Get all platforms feed."""
    try:
        repo = ApplicationRepository(session)
        apps = await repo.get_all_apps()
        return apps
    except Exception as e:
        logger.error(f"Failed to get all feed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
