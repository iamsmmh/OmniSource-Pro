"""Database and feed backup procedures.

Two backup artifacts are produced per run into ``BACKUP_DIR``:

1. **Database dump** — ``pg_dump -Fc`` against the configured PostgreSQL URL.
   Falls back to a no-op report when the database is not PostgreSQL (e.g.
   SQLite in development), so scheduling a backup is always safe.
2. **Feed snapshot** — a gzip tarball of the feeds directory.

Old artifacts beyond ``BACKUP_KEEP`` are pruned after each run (newest kept).
Backups never run through the async engine; they shell out to pg_dump so the
dump uses PostgreSQL's native custom format (compressed, restorable with
``pg_restore``).
"""

import asyncio
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings

logger = get_logger(__name__)


class BackupResult:
    """Outcome summary of one backup run."""

    def __init__(self) -> None:
        self.started_at = datetime.now(UTC)
        self.database_backup: str | None = None
        self.feeds_backup: str | None = None
        self.errors: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "database_backup": self.database_backup,
            "feeds_backup": self.feeds_backup,
            "errors": self.errors,
            "ok": not self.errors,
        }


def _postgres_dump_url(database_url: str) -> tuple[str | None, str]:
    """Return (pg-compatible URL, original). None when not PostgreSQL."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql://", 1), database_url
    if database_url.startswith("postgresql://") or database_url.startswith("postgres://"):
        return database_url, database_url
    return None, database_url


def prune_old_backups(backup_dir: Path, prefix: str, keep: int) -> int:
    """Delete the oldest artifacts with ``prefix`` beyond ``keep``. Returns pruned count."""
    artifacts = sorted(backup_dir.glob(f"{prefix}*"), key=lambda p: p.stat().st_mtime, reverse=True)
    pruned = 0
    for stale in artifacts[keep:]:
        try:
            stale.unlink()
            pruned += 1
        except OSError as exc:
            logger.warning("Could not prune %s: %s", stale, exc)
    return pruned


async def run_database_backup(output_path: Path) -> bool:
    """Run pg_dump into ``output_path``; True on success."""
    settings = get_settings()
    dump_url, original = _postgres_dump_url(settings.database.DATABASE_URL)
    if dump_url is None:
        logger.info(
            "Skipping database backup: not a PostgreSQL URL (%s...)", original.split("://")[0]
        )
        return False

    process = await asyncio.create_subprocess_exec(
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--file",
        str(output_path),
        dump_url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        message = stderr.decode(errors="replace").strip() or f"pg_dump exited {process.returncode}"
        logger.error("pg_dump failed: %s", message)
        output_path.unlink(missing_ok=True)
        raise RuntimeError(message)
    logger.info("Database backup written to %s", output_path)
    return True


def backup_feeds(feeds_dir: Path, output_path: Path) -> bool:
    """Archive the feeds directory into a gzipped tarball."""
    if not feeds_dir.exists() or not any(feeds_dir.iterdir()):
        logger.info("No feeds to back up at %s", feeds_dir)
        return False
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(feeds_dir, arcname=feeds_dir.name)
    logger.info("Feeds backup written to %s", output_path)
    return True


async def run_backup(
    backup_dir: str | Path | None = None, keep: int | None = None
) -> dict[str, Any]:
    """Execute a full backup cycle: database dump + feeds snapshot + pruning."""
    settings = get_settings()
    target_dir = Path(backup_dir or settings.database.BACKUP_DIR)
    keep_count = keep if keep is not None else settings.database.BACKUP_KEEP
    target_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    result = BackupResult()

    db_path = target_dir / f"db-{stamp}.dump"
    try:
        if await run_database_backup(db_path):
            result.database_backup = str(db_path)
    except Exception as exc:
        logger.exception("Database backup failed")
        result.errors.append(f"database: {exc}")

    feeds_path = target_dir / f"feeds-{stamp}.tar.gz"
    try:
        feeds_dir = Path(settings.feeds.FEEDS_DIR)
        await asyncio.to_thread(backup_feeds, feeds_dir, feeds_path)
        if feeds_path.exists():
            result.feeds_backup = str(feeds_path)
    except Exception as exc:
        logger.exception("Feeds backup failed")
        result.errors.append(f"feeds: {exc}")

    try:
        prune_old_backups(target_dir, "db-", keep_count)
        prune_old_backups(target_dir, "feeds-", keep_count)
    except Exception as exc:
        result.errors.append(f"prune: {exc}")

    if result.errors:
        logger.error("Backup completed with errors: %s", result.errors)
    else:
        logger.info("Backup completed: %s", result.to_dict())
    return result.to_dict()


__all__ = ["BackupResult", "backup_feeds", "prune_old_backups", "run_backup", "run_database_backup"]
