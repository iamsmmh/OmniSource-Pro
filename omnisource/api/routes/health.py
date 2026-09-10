"""
Health check API routes for OmniSource.
"""

from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings
from omnisource.connectors.base import ConnectorHealth

logger = get_logger(__name__)

router = APIRouter()


@router.get("", response_model=dict[str, Any])
async def health() -> dict[str, Any]:
    """
    Full health check endpoint.

    Returns the health status of all components.
    """
    health_status: dict = {
        "status": "healthy",
        "timestamp": None,
        "components": {},
    }

    # Check database
    try:
        from omnisource.core.database.base import get_async_engine

        engine = get_async_engine()
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        health_status["components"]["database"] = {
            "status": "healthy",
            "type": "postgresql",
        }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    # Check Redis
    try:
        import redis.asyncio as redis

        settings = get_settings()
        r = redis.from_url(settings.redis.REDIS_URL)
        await r.ping()
        await r.aclose()
        health_status["components"]["redis"] = {
            "status": "healthy",
            "type": "redis",
        }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["redis"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    # Check Meilisearch
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
        health_status["components"]["meilisearch"] = {
            "status": "healthy",
            "type": "meilisearch",
        }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["meilisearch"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    # Check GitHub connector
    try:
        from omnisource.connectors.github import GitHubConnector

        connector = GitHubConnector()
        await connector.initialize()
        health = await connector.health_check()
        await connector.close()

        health_status["components"]["github"] = {
            "status": "healthy" if health.healthy else "unhealthy",
            "type": "source",
            "latency_ms": health.latency_ms,
            "error_rate": health.error_rate,
        }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["github"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    from datetime import UTC, datetime

    health_status["timestamp"] = datetime.now(UTC).isoformat() + "Z"

    return health_status


@router.get("/live", response_model=dict[str, str])
async def health_live() -> dict[str, str]:
    """
    Liveness probe.

    Simple endpoint to check if the service is running.
    """
    return {"status": "alive"}


@router.get("/ready", response_model=dict[str, Any])
async def health_ready() -> dict[str, Any]:
    """
    Readiness probe.

    Checks if the service is ready to accept requests.
    """
    ready_status = {
        "status": "ready",
        "database": False,
        "redis": False,
    }

    # Check database
    try:
        from omnisource.core.database.base import get_async_engine

        engine = get_async_engine()
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        ready_status["database"] = True
    except Exception:
        ready_status["status"] = "not_ready"
        ready_status["database"] = False

    # Check Redis
    try:
        import redis.asyncio as redis

        settings = get_settings()
        r = redis.from_url(settings.redis.REDIS_URL)
        await r.ping()
        await r.aclose()
        ready_status["redis"] = True
    except Exception:
        ready_status["status"] = "not_ready"
        ready_status["redis"] = False

    return ready_status


@router.get("/sources", response_model=list[ConnectorHealth])
async def health_sources() -> list[ConnectorHealth]:
    """
    Get health status of all sources.

    Returns health information for each configured source.
    """
    health_list = []

    # Check GitHub
    try:
        from omnisource.connectors.github import GitHubConnector

        connector = GitHubConnector()
        await connector.initialize()
        health = await connector.health_check()
        await connector.close()
        health_list.append(health)
    except Exception as e:
        health_list.append(
            ConnectorHealth(
                source="github",
                healthy=False,
                last_error=str(e),
            )
        )

    return health_list
