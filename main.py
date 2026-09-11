#!/usr/bin/env python3
"""
OmniSource main entry point.

This file provides the main entry points for running OmniSource in different modes.
"""

import asyncio
import sys
from typing import Optional

import click

from omnisource.config.settings import get_settings
from omnisource.config.logging import setup_logging, get_logger

logger = get_logger(__name__)


@click.group(
    name="omnisource",
    help="OmniSource - Autonomous Open-Source Software Discovery Platform",
)
@click.version_option(version="0.1.0", prog_name="omnisource")
def cli():
    """Main entry point."""
    settings = get_settings()
    setup_logging(log_level=settings.LOG_LEVEL)
    logger.info(f"OmniSource v{settings.APP_VERSION}")


@cli.command(name="api", help="Run the API server")
@click.option(
    "--host",
    default=None,
    help="Host to bind to",
)
@click.option(
    "--port",
    type=int,
    default=None,
    help="Port to listen on",
)
@click.option(
    "--reload",
    is_flag=True,
    default=False,
    help="Enable auto-reload for development",
)
def run_api(host: Optional[str], port: Optional[int], reload: bool) -> None:
    """Run the FastAPI server."""
    import uvicorn
    
    settings = get_settings()
    
    host = host or settings.api.API_HOST
    port = port or settings.api.API_PORT
    
    logger.info(f"Starting API server on {host}:{port}")
    
    uvicorn.run(
        "omnisource.api.main:app",
        host=host,
        port=port,
        reload=reload or settings.api.API_DEBUG,
        workers=settings.api.API_WORKERS,
        log_level=settings.LOG_LEVEL.lower(),
    )


@cli.command(name="worker", help="Run the background worker")
@click.option("--source", default="github", show_default=True, help="Source type to sync (e.g. github, gitlab, fdroid)")
def run_worker(source: str) -> None:
    """Run the background job worker."""
    import asyncio

    logger.info("Starting OmniSource worker")

    async def _run() -> None:
        from omnisource.automation.jobs import run_indexing, run_sync, run_validation
        from omnisource.core.database.session import create_session

        async with create_session() as session:
            await run_sync(session, source_type=source)
            await run_validation(session)
            await run_indexing(session)
        logger.info("Worker pipeline complete")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Worker stopped")


@cli.command(name="discover", help="Discover new repositories from a source")
@click.option("--source", default="github", show_default=True, help="Source type (e.g. github, gitlab, fdroid)")
@click.option("--query", default=None, help="Search query override for the connector")
@click.option("--limit", type=int, default=None, help="Max repositories to discover this pass")
def run_discover(source: str, query: str | None, limit: int | None) -> None:
    """Run a discovery pass for the given source."""
    import asyncio

    from omnisource.automation.jobs import run_discovery
    from omnisource.core.database.session import create_session

    logger.info("Starting OmniSource discovery")

    async def _run() -> None:
        async with create_session() as session:
            result = await run_discovery(session, source_type=source, query=query, limit=limit)
            logger.info("Discovery result: %s", result)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Discovery stopped")


@cli.command(name="scheduler", help="Run the periodic scheduler")
def run_scheduler() -> None:
    """Run the periodic job scheduler."""
    import asyncio

    from omnisource.automation.scheduler import build_default_scheduler

    logger.info("Starting OmniSource scheduler")

    async def _run() -> None:
        scheduler = build_default_scheduler()
        await scheduler.run_forever()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Scheduler stopped")


@cli.command(name="bootstrap", help="Initialize the database")
def bootstrap() -> None:
    """Initialize the database."""
    import asyncio

    from omnisource.core.database.base import init_db
    from omnisource.cli.main import _create_default_data

    logger.info("Initializing database...")

    async def _run() -> None:
        await init_db()
        logger.info("Database initialized")

        await _create_default_data()
        logger.info("Default data created")

    try:
        asyncio.run(_run())
    except Exception as e:
        logger.error(f"Bootstrap failed: {e}")
        sys.exit(1)


@cli.command(name="migrate", help="Run database migrations")
def migrate() -> None:
    """Run database migrations."""
    import subprocess
    
    logger.info("Running database migrations...")
    
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Migrations completed")
        logger.debug(result.stdout)
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Migrations failed: {e.stderr}")
        sys.exit(1)


def main():
    """Main entry point."""
    cli()


# Import _create_default_data for bootstrap command
async def _create_default_data() -> None:
    """Create default data in the database."""
    from omnisource.core.models.platform import Platform, Architecture
    from omnisource.core.models.category import Category, CategoryType, TAXONOMY
    from omnisource.core.models.source import Source, SourceType
    from omnisource.core.database.session import get_session
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    
    async with get_session() as session:
        # Create default platforms
        platforms = [
            {"platform_type": "ios", "name": "iOS", "display_name": "iOS", "icon": "ios"},
            {"platform_type": "ipados", "name": "iPadOS", "display_name": "iPadOS", "icon": "ipados"},
            {"platform_type": "android", "name": "Android", "display_name": "Android", "icon": "android"},
            {"platform_type": "windows", "name": "Windows", "display_name": "Windows", "icon": "windows"},
            {"platform_type": "macos", "name": "macOS", "display_name": "macOS", "icon": "macos"},
            {"platform_type": "linux", "name": "Linux", "display_name": "Linux", "icon": "linux"},
        ]
        
        for platform_data in platforms:
            existing = await session.execute(
                select(Platform).where(Platform.platform_type == platform_data["platform_type"])
            )
            if existing.scalar_one_or_none() is None:
                platform = Platform(**platform_data)
                session.add(platform)
        
        # Create default architectures
        architectures = [
            {"architecture_type": "arm64", "name": "ARM64", "display_name": "ARM64", "aliases": ["aarch64"]},
            {"architecture_type": "x86_64", "name": "x86_64", "display_name": "x86_64", "aliases": ["amd64", "x64"]},
            {"architecture_type": "x86", "name": "x86", "display_name": "x86", "aliases": ["i386", "i686"]},
            {"architecture_type": "universal", "name": "Universal", "display_name": "Universal", "aliases": []},
            {"architecture_type": "universal2", "name": "Universal2", "display_name": "Universal 2", "aliases": []},
            {"architecture_type": "armv7", "name": "ARMV7", "display_name": "ARMV7", "aliases": []},
            {"architecture_type": "any", "name": "Any", "display_name": "Any Architecture", "aliases": []},
        ]
        
        for arch_data in architectures:
            existing = await session.execute(
                select(Architecture).where(Architecture.architecture_type == arch_data["architecture_type"])
            )
            if existing.scalar_one_or_none() is None:
                arch = Architecture(**arch_data)
                session.add(arch)
        
        # Create default categories
        for i, (cat_type, cat_info) in enumerate(TAXONOMY.items()):
            existing = await session.execute(
                select(Category).where(Category.category_type == cat_type.value)
            )
            if existing.scalar_one_or_none() is None:
                category = Category(
                    category_type=cat_type.value,
                    name=cat_info["name"],
                    slug=cat_type.value,
                    description=cat_info["description"],
                    sort_order=i,
                )
                session.add(category)
        
        # Create default sources
        sources = [
            {"name": "GitHub", "source_type": SourceType.GITHUB, "base_url": "https://github.com", "api_url": "https://api.github.com", "is_active": True},
            {"name": "GitLab", "source_type": SourceType.GITLAB, "base_url": "https://gitlab.com", "api_url": "https://gitlab.com/api/v4", "is_active": True},
            {"name": "Codeberg", "source_type": SourceType.CODEBERG, "base_url": "https://codeberg.org", "api_url": "https://codeberg.org/api/v1", "is_active": True},
        ]
        
        for source_data in sources:
            existing = await session.execute(
                select(Source).where(Source.name == source_data["name"])
            )
            if existing.scalar_one_or_none() is None:
                source = Source(**source_data)
                session.add(source)
        
        await session.commit()


if __name__ == "__main__":
    main()


@cli.command(name="backup", help="Run a database and feeds backup cycle")
@click.option("--dir", "backup_dir", default=None, help="Backup output directory")
@click.option("--keep", type=int, default=None, help="Backups to retain per artifact type")
def backup(backup_dir: Optional[str], keep: Optional[int]) -> None:
    """Run a backup cycle (database dump + feeds snapshot) and prune old artifacts."""
    import asyncio

    from omnisource.core.backup import run_backup

    result = asyncio.run(run_backup(backup_dir=backup_dir, keep=keep))
    click.echo(result)

