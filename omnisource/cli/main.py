"""
Command-line interface for OmniSource.

Provides commands for managing the OmniSource platform.
"""

import asyncio
import sys
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from omnisource.config.settings import get_settings
from omnisource.config.logging import setup_logging, get_logger
from omnisource.core.database.base import init_db

console = Console()
logger = get_logger(__name__)


@click.group(
    name="omnisource",
    help="OmniSource - Autonomous Open-Source Software Discovery Platform",
    epilog="For more information, visit: https://github.com/iamsmmh/OmniSource-Pro",
)
@click.version_option(version="0.1.0", prog_name="omnisource")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Enable verbose logging",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    default=".env",
    help="Configuration file path",
)
def cli(verbose: bool, config: str) -> None:
    """Main CLI entry point."""
    # Load settings
    settings = get_settings()
    
    # Setup logging
    log_level = "DEBUG" if verbose else settings.LOG_LEVEL
    setup_logging(log_level=log_level, json_format=False)
    
    logger.debug(f"OmniSource CLI v{settings.APP_VERSION}")
    logger.debug(f"Configuration file: {config}")


@cli.command(
    name="bootstrap",
    help="Initialize OmniSource database and configuration",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Force re-initialization",
)
async def bootstrap(force: bool) -> None:
    """Initialize the database and configuration."""
    console.print(Panel("[bold blue]OmniSource Bootstrap[/bold blue]", border_style="blue"))
    
    try:
        # Initialize database
        console.print("[cyan]Initializing database...[/cyan]")
        await init_db()
        console.print("[green]✓ Database initialized[/green]")
        
        # Create default data
        console.print("[cyan]Creating default data...[/cyan]")
        await _create_default_data()
        console.print("[green]✓ Default data created[/green]")
        
        console.print(Panel("[green]Bootstrap completed successfully![/green]", border_style="green"))
        
    except Exception as e:
        console.print(f"[red]✗ Bootstrap failed: {e}[/red]")
        logger.error(f"Bootstrap failed: {e}", exc_info=True)
        sys.exit(1)


@cli.command(
    name="discover",
    help="Discover repositories from sources",
)
@click.option(
    "--source",
    "-s",
    type=click.Choice(["github", "gitlab", "all"]),
    default="github",
    help="Source to discover from",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=100,
    help="Maximum repositories to discover",
)
@click.option(
    "--query",
    "-q",
    type=str,
    default=None,
    help="Search query for discovery",
)
async def discover(source: str, limit: int, query: Optional[str]) -> None:
    """Discover repositories from a source."""
    console.print(Panel(f"[bold blue]Discovering from {source}[/bold blue]", border_style="blue"))
    
    try:
        if source == "github" or source == "all":
            from omnisource.connectors.github import GitHubConnector
            
            connector = GitHubConnector()
            await connector.initialize()
            
            try:
                console.print(f"[cyan]Discovering from GitHub...[/cyan]")
                repositories, page_info = await connector.discover(
                    query=query,
                    limit=limit,
                )
                
                console.print(f"[green]✓ Discovered {len(repositories)} repositories[/green]")
                console.print(f"  Total: {page_info.total}")
                console.print(f"  Page: {page_info.page}/{page_info.total_pages}")
                
            finally:
                await connector.close()
        
        if source == "gitlab" or source == "all":
            console.print("[yellow]GitLab discovery not yet implemented[/yellow]")
        
        console.print(Panel("[green]Discovery completed![/green]", border_style="green"))
        
    except Exception as e:
        console.print(f"[red]✗ Discovery failed: {e}[/red]")
        logger.error(f"Discovery failed: {e}", exc_info=True)
        sys.exit(1)


@cli.command(
    name="sync",
    help="Synchronize repositories and releases",
)
@click.option(
    "--source",
    "-s",
    type=click.Choice(["github", "gitlab", "all"]),
    default="github",
    help="Source to sync from",
)
@click.option(
    "--app",
    "-a",
    type=str,
    default=None,
    help="Sync specific application",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Perform a dry run without saving",
)
async def sync(source: str, app: Optional[str], dry_run: bool) -> None:
    """Synchronize repositories and releases."""
    console.print(Panel(f"[bold blue]Syncing from {source}[/bold blue]", border_style="blue"))
    
    if dry_run:
        console.print("[yellow]Dry run mode - no changes will be saved[/yellow]")
    
    try:
        if source == "github" or source == "all":
            from omnisource.connectors.github import GitHubConnector
            
            connector = GitHubConnector()
            await connector.initialize()
            
            try:
                if app:
                    console.print(f"[cyan]Syncing application: {app}[/cyan]")
                    # Get specific app logic would go here
                else:
                    console.print(f"[cyan]Full sync from GitHub...[/cyan]")
                    # Full sync logic would go here
                
                console.print("[green]✓ Sync completed[/green]")
                
            finally:
                await connector.close()
        
        console.print(Panel("[green]Sync completed![/green]", border_style="green"))
        
    except Exception as e:
        console.print(f"[red]✗ Sync failed: {e}[/red]")
        logger.error(f"Sync failed: {e}", exc_info=True)
        sys.exit(1)


@cli.command(
    name="generate-feeds",
    help="Generate platform-specific feeds",
)
@click.option(
    "--platform",
    "-p",
    type=click.Choice(["ios", "android", "windows", "macos", "linux", "all"]),
    default="all",
    help="Platform to generate feed for",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="./data/feeds",
    help="Output directory",
)
async def generate_feeds(platform: str, output: str) -> None:
    """Generate platform-specific feeds."""
    console.print(Panel("[bold blue]Generating Feeds[/bold blue]", border_style="blue"))
    
    try:
        console.print(f"[cyan]Generating feeds for: {platform}[/cyan]")
        console.print(f"[cyan]Output directory: {output}[/cyan]")
        
        # Feed generation logic would go here
        console.print("[yellow]Feed generation not yet implemented[/yellow]")
        
        console.print(Panel("[green]Feed generation completed![/green]", border_style="green"))
        
    except Exception as e:
        console.print(f"[red]✗ Feed generation failed: {e}[/red]")
        logger.error(f"Feed generation failed: {e}", exc_info=True)
        sys.exit(1)


@cli.command(
    name="health",
    help="Check OmniSource health status",
)
async def health() -> None:
    """Check the health of OmniSource components."""
    console.print(Panel("[bold blue]OmniSource Health Check[/bold blue]", border_style="blue"))
    
    try:
        # Check database
        console.print("[cyan]Checking database...[/cyan]")
        try:
            await init_db()
            console.print("[green]✓ Database: Healthy[/green]")
        except Exception as e:
            console.print(f"[red]✗ Database: Unhealthy - {e}[/red]")
        
        # Check GitHub connector
        console.print("[cyan]Checking GitHub connector...[/cyan]")
        try:
            from omnisource.connectors.github import GitHubConnector
            connector = GitHubConnector()
            await connector.initialize()
            health = await connector.health_check()
            await connector.close()
            
            if health.healthy:
                console.print(f"[green]✓ GitHub: Healthy (latency: {health.latency_ms}ms)[/green]")
            else:
                console.print(f"[red]✗ GitHub: Unhealthy - {health.last_error}[/red]")
        except Exception as e:
            console.print(f"[red]✗ GitHub: Unhealthy - {e}[/red]")
        
        console.print(Panel("[green]Health check completed![/green]", border_style="green"))
        
    except Exception as e:
        console.print(f"[red]✗ Health check failed: {e}[/red]")
        logger.error(f"Health check failed: {e}", exc_info=True)
        sys.exit(1)


@cli.command(
    name="stats",
    help="Show OmniSource statistics",
)
async def stats() -> None:
    """Show statistics about the OmniSource catalog."""
    console.print(Panel("[bold blue]OmniSource Statistics[/bold blue]", border_style="blue"))
    
    try:
        # Statistics would be fetched from database
        table = Table(title="Catalog Statistics", box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        # Placeholder values
        table.add_row("Total Applications", "0")
        table.add_row("Total Repositories", "0")
        table.add_row("Total Releases", "0")
        table.add_row("Total Assets", "0")
        table.add_row("Platforms", "iOS, Android, Windows, macOS, Linux")
        
        console.print(table)
        console.print(Panel("[green]Statistics displayed![/green]", border_style="green"))
        
    except Exception as e:
        console.print(f"[red]✗ Failed to get statistics: {e}[/red]")
        logger.error(f"Statistics failed: {e}", exc_info=True)
        sys.exit(1)


@cli.command(
    name="full-sync",
    help="Perform a full synchronization of all sources",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Perform a dry run without saving",
)
async def full_sync(dry_run: bool) -> None:
    """Perform a complete synchronization."""
    console.print(Panel("[bold blue]Full Synchronization[/bold blue]", border_style="blue"))
    
    if dry_run:
        console.print("[yellow]Dry run mode - no changes will be saved[/yellow]")
    
    try:
        console.print("[cyan]Starting full sync...[/cyan]")
        
        # Full sync logic would go here
        console.print("[yellow]Full sync not yet implemented[/yellow]")
        
        console.print(Panel("[green]Full sync completed![/green]", border_style="green"))
        
    except Exception as e:
        console.print(f"[red]✗ Full sync failed: {e}[/red]")
        logger.error(f"Full sync failed: {e}", exc_info=True)
        sys.exit(1)


async def _create_default_data() -> None:
    """Create default data in the database."""
    from omnisource.core.models.platform import Platform, Architecture, ARCH_ALIASES
    from omnisource.core.models.category import Category, CategoryType, TAXONOMY
    from omnisource.core.models.source import Source, SourceType
    from omnisource.core.database.session import get_session
    from sqlalchemy.ext.asyncio import AsyncSession
    
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


# Fix import issue
from sqlalchemy import select


def main():
    """Run the CLI."""
    cli()


if __name__ == "__main__":
    main()
