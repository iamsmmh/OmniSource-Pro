"""Database session management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Generator, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from omnisource.config.settings import get_settings
from omnisource.core.database.base import get_async_session


@asynccontextmanager
async def create_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Create and manage an async database session.
    
    Yields:
        An async SQLAlchemy session
    """
    session_maker = get_async_session()
    session = session_maker()
    
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session with automatic commit/rollback.
    
    Yields:
        An async SQLAlchemy session
    """
    session_maker = get_async_session()
    session = session_maker()
    
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_async_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Alternative session context manager."""
    session_maker = get_async_session()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def create_sync_session() -> Session:
    """
    Create a synchronous database session (for migrations and CLI tools).
    
    Note: This is a workaround for Alembic which doesn't support async.
    
    Returns:
        A synchronous SQLAlchemy session
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    settings = get_settings()
    
    # Convert async URL to sync URL
    url = str(settings.database.DATABASE_URL)
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://")
    
    engine = create_engine(
        url,
        pool_size=settings.database.DATABASE_POOL_SIZE,
        max_overflow=settings.database.DATABASE_MAX_OVERFLOW,
        pool_timeout=settings.database.DATABASE_POOL_TIMEOUT,
        echo=settings.database.DATABASE_ECHO,
    )
    
    SessionLocal = sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    
    return SessionLocal()
