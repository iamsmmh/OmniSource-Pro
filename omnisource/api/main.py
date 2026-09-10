"""
FastAPI application for OmniSource.

Provides REST API endpoints for OmniStore and other clients.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down OmniSource API...")
    try:
        await close_db()
        logger.info("Database closed")
    except Exception as e:
        logger.error(f"Failed to close database: {e}")


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

# Add CORS middleware
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.API_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle validation errors."""
    logger.warning(f"Validation error: {exc}")
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation Error",
            "detail": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected errors."""
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": str(exc),
        },
    )


# Include API routes
from omnisource.api.routes import (
    apps_router,
    categories_router,
    developers_router,
    feeds_router,
    health_router,
    latest_router,
    platforms_router,
    releases_router,
    search_router,
    stats_router,
    trending_router,
)

app.include_router(apps_router, prefix="/api/v1/apps", tags=["apps"])
app.include_router(search_router, prefix="/api/v1/search", tags=["search"])
app.include_router(releases_router, prefix="/api/v1/releases", tags=["releases"])
app.include_router(categories_router, prefix="/api/v1/categories", tags=["categories"])
app.include_router(platforms_router, prefix="/api/v1/platforms", tags=["platforms"])
app.include_router(developers_router, prefix="/api/v1/developers", tags=["developers"])
app.include_router(trending_router, prefix="/api/v1/trending", tags=["trending"])
app.include_router(latest_router, prefix="/api/v1/latest", tags=["latest"])
app.include_router(stats_router, prefix="/api/v1/stats", tags=["stats"])
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(feeds_router, prefix="/feeds", tags=["feeds"])


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
