"""Database initialization and engine management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from omnisource.config.settings import get_settings

# Global engine instances
_engine: Optional[AsyncEngine] = None
_async_session_maker: Optional[async_sessionmaker] = None


def get_async_engine() -> AsyncEngine:
    """Get or create the async database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database.DATABASE_URL,
            pool_size=settings.database.DATABASE_POOL_SIZE,
            max_overflow=settings.database.DATABASE_MAX_OVERFLOW,
            pool_timeout=settings.database.DATABASE_POOL_TIMEOUT,
            echo=settings.database.DATABASE_ECHO,
        )
    return _engine


def get_async_session() -> async_sessionmaker:
    """Get or create the async session factory."""
    global _async_session_maker
    if _async_session_maker is None:
        engine = get_async_engine()
        _async_session_maker = async_sessionmaker(
            engine,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_maker


async def init_db() -> AsyncEngine:
    """
    Initialize the database.
    
    Creates tables and sets up the database schema.
    
    Returns:
        The async engine instance
    """
    engine = get_async_engine()
    
    # Import all models to register them with SQLAlchemy
    from omnisource.core.models import Base  # noqa: F401
    
    async with engine.begin() as conn:
        # Enable UUID extension if PostgreSQL
        if "postgresql" in str(engine.url):
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS "pgcrypto"""))
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    
    return engine


async def close_db() -> None:
    """Close the database connection."""
    global _engine, _async_session_maker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_maker = None


@asynccontextmanager
async def get_db_lifespan() -> AsyncGenerator[AsyncEngine, None]:
    """
    Context manager for database lifespan (used with FastAPI).
    
    Yields:
        The async engine
    """
    engine = get_async_engine()
    try:
        yield engine
    finally:
        await close_db()


def get_sync_engine() -> Optional[AsyncEngine]:
    """Get the sync engine (for migrations)."""
    return _engine
