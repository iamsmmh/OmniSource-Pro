"""Liveness, readiness, dependency, and external-source health endpoints."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text

from omnisource.api.dependencies import get_db
from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings
from omnisource.connectors.base import ConnectorHealth
from omnisource.crawler.source_health import SourceHealthService

logger = get_logger(__name__)

router = APIRouter()


async def _database_component() -> tuple[bool, dict[str, str]]:
    """Check the primary database without exposing driver/provider failures."""
    try:
        from omnisource.core.database.base import get_async_engine

        engine = get_async_engine()
        async with engine.begin() as connection:
            await connection.execute(text("SELECT 1"))
        return True, {"status": "healthy", "type": "postgresql"}
    except Exception:
        logger.warning("Database health check failed", exc_info=True)
        return False, {"status": "unhealthy", "error": "database_unavailable"}


async def _redis_component() -> tuple[bool, dict[str, str]]:
    """Check Redis and close its short-lived probe client in every outcome."""
    client = None
    try:
        import redis.asyncio as redis

        client = redis.from_url(get_settings().redis.REDIS_URL)
        await client.ping()
        return True, {"status": "healthy", "type": "redis"}
    except Exception:
        logger.warning("Redis health check failed", exc_info=True)
        return False, {"status": "unhealthy", "error": "redis_unavailable"}
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                logger.debug("Redis health probe client close failed", exc_info=True)


async def _meilisearch_component() -> tuple[bool, dict[str, str]]:
    """Check the search service, returning a stable public error code only."""
    try:
        import meilisearch

        settings = get_settings()
        client = meilisearch.Client(
            settings.meilisearch.MEILISEARCH_URL,
            settings.meilisearch.MEILISEARCH_MASTER_KEY,
        )
        result = client.health()
        if hasattr(result, "__await__"):
            await result
        return True, {"status": "healthy", "type": "meilisearch"}
    except Exception:
        logger.warning("Meilisearch health check failed", exc_info=True)
        return False, {"status": "unhealthy", "error": "search_unavailable"}


@router.get("", response_model=dict[str, Any])
async def health() -> dict[str, Any]:
    """Return bounded checks for owned dependencies.

    Source probes intentionally live at ``/health/sources`` and in the
    scheduled source-health job. Keeping external providers out of the main
    probe prevents GitHub or another upstream from taking the API deployment
    itself out of rotation.
    """
    database_ok, database = await _database_component()
    redis_ok, redis = await _redis_component()
    search_ok, search = await _meilisearch_component()
    healthy = database_ok and redis_ok and search_ok
    return {
        "status": "healthy" if healthy else "degraded",
        "timestamp": datetime.now(UTC).isoformat(),
        "components": {
            "database": database,
            "redis": redis,
            "meilisearch": search,
            "sources": {"status": "checked_separately", "type": "external_sources"},
        },
    }


@router.get("/live", response_model=dict[str, str])
async def health_live() -> dict[str, str]:
    """Liveness probe: process is accepting HTTP requests."""
    return {"status": "alive"}


@router.get("/ready", response_model=dict[str, Any])
async def health_ready() -> JSONResponse:
    """Readiness probe for mandatory database and cache dependencies."""
    database_ok, _ = await _database_component()
    redis_ok, _ = await _redis_component()
    is_ready = database_ok and redis_ok
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={
            "status": "ready" if is_ready else "not_ready",
            "database": database_ok,
            "redis": redis_ok,
        },
    )


@router.get("/sources", response_model=list[ConnectorHealth])
async def health_sources(session=Depends(get_db)) -> list[ConnectorHealth]:
    """Concurrently probe every registered connector and persist safe telemetry."""
    try:
        return await SourceHealthService(
            session, timeout_seconds=get_settings().sources.SOURCE_HEALTH_CHECK_TIMEOUT
        ).check_all()
    except Exception as exc:
        logger.error("Source health persistence failed", exc_info=True)
        raise HTTPException(status_code=503, detail="Source health is unavailable") from exc
