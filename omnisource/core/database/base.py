"""Database initialization and engine management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from omnisource.config.settings import get_settings

# Global engine instances
_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker | None = None


def get_async_engine() -> AsyncEngine:
    """Get or create the async database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        url = str(settings.database.DATABASE_URL)

        engine_kwargs: dict = {
            "echo": settings.database.DATABASE_ECHO,
        }
        # Pool arguments are only valid for PostgreSQL (asyncpg) connections.
        if url.startswith("postgresql"):
            engine_kwargs.update(
                pool_size=settings.database.DATABASE_POOL_SIZE,
                max_overflow=settings.database.DATABASE_MAX_OVERFLOW,
                pool_timeout=settings.database.DATABASE_POOL_TIMEOUT,
            )

        _engine = create_async_engine(url, **engine_kwargs)

        # SQLite: enable WAL so API readers are not blocked by the
        # collection worker's long write transactions, and wait (instead of
        # failing) briefly on lock contention.
        if url.startswith("sqlite"):
            from sqlalchemy import event

            @event.listens_for(_engine.sync_engine, "connect")
            def _set_sqlite_pragmas(dbapi_connection, connection_record):  # pragma: no cover
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA busy_timeout=30000")
                    cursor.execute("PRAGMA foreign_keys=ON")
                finally:
                    cursor.close()

    return _engine


def get_engine() -> AsyncEngine:
    """Alias for get_async_engine (compatibility)."""
    return get_async_engine()


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
    from omnisource.core.models import Base

    async with engine.begin() as conn:
        # Enable UUID extension if PostgreSQL
        if "postgresql" in str(engine.url):
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))

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


def get_sync_engine() -> AsyncEngine | None:
    """Get the sync engine (for migrations)."""
    return _engine
