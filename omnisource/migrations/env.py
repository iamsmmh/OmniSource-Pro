"""
Alembic environment configuration for OmniSource.
"""

from logging.config import fileConfig
from typing import Any

from alembic import context

# Import settings
from omnisource.config.settings import get_settings

# This is the Alembic Config object
config = context.config

# Update config from settings
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set SQLAlchemy URL from settings
default_url = get_settings().database.DATABASE_URL
if default_url.startswith("postgresql+asyncpg://"):
    # Convert async URL to sync URL for Alembic
    sync_url = default_url.replace("postgresql+asyncpg://", "postgresql://")
    config.set_main_option("sqlalchemy.url", sync_url)
else:
    config.set_main_option("sqlalchemy.url", default_url)

# Add your model's MetaData object here for 'autogenerate' support
from omnisource.core.database.base import get_async_engine
from omnisource.core.models import Base

target_metadata = Base.metadata

# Other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("something")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    ``get_async_engine`` creates the shared engine when Alembic is invoked
    directly, so ``alembic upgrade head`` works before the API has started.
    Migrations are executed through ``run_sync`` on its async connection.
    """
    import asyncio

    connectable = get_async_engine()

    def do_run_migrations(connection: Any) -> None:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    async def _run_async_migrations() -> None:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
        await connectable.dispose()

    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
