"""FastAPI dependency providers for OmniSource."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.core.database.session import create_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session, committing on success and rolling back on error."""
    async with create_session() as session:
        yield session
