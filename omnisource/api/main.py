"""
FastAPI application for OmniSource.

Provides REST API endpoints for OmniStore and other clients.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.middleware.gzip import GZipMiddleware

from omnisource.config.logging import get_logger, setup_logging
from omnisource.config.settings import get_settings
from omnisource.core.database.base import close_db, init_db

logger = get_logger(__name__)

# Initialize logging
setup_logging(log_level=get_settings().LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting OmniSource API...")

    try:
        # Initialize database
        await init_db()
        logger.info("Database initialized")
    except Exception:
        logger.error("Database initialization failed", exc_info=True)
        raise

    yield

    # Shutdown
    logger.info("Shutting down OmniSource API...")
    try:
        await close_db()
        logger.info("Database closed")
    except Exception:
        logger.error("Database shutdown failed", exc_info=True)
    finally:
        from omnisource.observability import shutdown_observability

        shutdown_observability(app)


# Create FastAPI app
app = FastAPI(
    title="OmniSource API",
    description="Autonomous open-source software discovery, indexing, validation, metadata, and feed platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS is opt-in. Credentials are never used with a wildcard origin.
settings = get_settings()
from omnisource.observability import configure_observability

configure_observability(app, settings)
if settings.api.API_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.API_CORS_ORIGINS,
        allow_credentials="*" not in settings.api.API_CORS_ORIGINS,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Content-Type",
            "If-None-Match",
            "X-API-Key",
            "X-OmniStore-Subject",
        ],
        expose_headers=["ETag", "Cache-Control", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )


# Global exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle validation errors."""
    logger.warning("Request validation failed", extra={"operation": "request_validation"})
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation Error",
            "detail": [
                {key: value for key, value in error.items() if key != "input"}
                for error in exc.errors()
            ],
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected errors."""
    logger.error("Unhandled API exception", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred",
        },
    )


# Include API routes
from omnisource.api.routes import (
    analytics_router,
    apps_router,
    categories_router,
    collections_router,
    developers_router,
    favorites_router,
    feeds_router,
    health_router,
    integration_router,
    latest_router,
    platforms_router,
    popular_router,
    recommendations_router,
    releases_router,
    search_router,
    security_router,
    stats_router,
    trending_router,
    trust_router,
    webhook_management_router,
)

app.include_router(apps_router, prefix="/api/v1/apps", tags=["apps"])
app.include_router(search_router, prefix="/api/v1/search", tags=["search"])
app.include_router(releases_router, prefix="/api/v1/releases", tags=["releases"])
app.include_router(categories_router, prefix="/api/v1/categories", tags=["categories"])
app.include_router(platforms_router, prefix="/api/v1/platforms", tags=["platforms"])
app.include_router(developers_router, prefix="/api/v1/developers", tags=["developers"])
app.include_router(trending_router, prefix="/api/v1/trending", tags=["trending"])
app.include_router(latest_router, prefix="/api/v1/latest", tags=["latest"])
app.include_router(popular_router, prefix="/api/v1/popular", tags=["popular"])
app.include_router(stats_router, prefix="/api/v1/stats", tags=["stats"])
app.include_router(
    recommendations_router, prefix="/api/v1/recommendations", tags=["recommendations"]
)
app.include_router(collections_router, prefix="/api/v1/collections", tags=["collections"])
app.include_router(favorites_router, prefix="/api/v1/favorites", tags=["favorites"])
app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(trust_router, prefix="/api/v1/trust", tags=["trust"])
app.include_router(security_router, prefix="/api/v1/security", tags=["security"])
app.include_router(integration_router, prefix="/api/v1", tags=["omnistore-integration"])
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(feeds_router, prefix="/feeds", tags=["feeds"])

# Rate limiting, metrics, and API-key auth (order matters: auth added outermost runs first)
from omnisource.api.cache import ResponseCacheMiddleware
from omnisource.api.metrics import CONTENT_TYPE_LATEST, MetricsMiddleware, render_metrics
from omnisource.api.rate_limit import RateLimitMiddleware, build_rate_limiter
from omnisource.api.routes import admin_router, webhooks_router
from omnisource.api.routes.admin import admin_dashboard_html
from omnisource.api.security import (
    configure_app_auth,
    require_api_key,
)

# Last-added middleware runs outermost in Starlette; keep rate limiting ahead
# of the response cache so cached hits still count against client quotas.
app.add_middleware(ResponseCacheMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(RateLimitMiddleware, limiter=build_rate_limiter())
configure_app_auth(app)
# Compression outermost: gzip JSON responses for clients that accept it.
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.get("/metrics", include_in_schema=False, tags=["observability"])
async def prometheus_metrics() -> Response:
    """Prometheus scrape endpoint."""
    return Response(content=render_metrics(), media_type=CONTENT_TYPE_LATEST)


@app.get("/admin", include_in_schema=False, tags=["admin"])
async def admin_dashboard() -> HTMLResponse:
    """Admin dashboard UI (data endpoints under /api/v1/admin require an API key)."""
    return HTMLResponse(content=admin_dashboard_html())


# Admin routes require a valid API key; webhook routes verify their own signatures
app.include_router(
    admin_router, prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_api_key)]
)
app.include_router(webhooks_router, prefix="/api/v1/webhooks", tags=["webhooks"])
app.include_router(
    webhook_management_router,
    prefix="/api/v1/webhooks",
    tags=["webhooks"],
    dependencies=[Depends(require_api_key)],
)


# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": "OmniSource",
        "version": "0.1.0",
        "description": "Autonomous open-source software discovery and distribution platform",
        "docs": "/docs",
        "health": "/health",
    }


# 404 handler
@app.get("/404", include_in_schema=False)
async def not_found():
    """404 handler."""
    raise HTTPException(status_code=404, detail="Not Found")
