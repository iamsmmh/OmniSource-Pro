"""Tests for backup procedures (no real pg_dump required)."""

from pathlib import Path

import pytest

from omnisource.core.backup import backup_feeds, prune_old_backups, run_backup

pytestmark = pytest.mark.asyncio


class TestFeedBackup:
    async def test_archives_feeds_directory(self, tmp_path: Path):
        feeds = tmp_path / "feeds"
        feeds.mkdir()
        (feeds / "android.json").write_text('{"apps": []}')
        (feeds / "windows.json").write_text('{"apps": []}')

        out = tmp_path / "feeds-snap.tar.gz"
        assert backup_feeds(feeds, out) is True
        assert out.exists() and out.stat().st_size > 0

    async def test_missing_feeds_returns_false(self, tmp_path: Path):
        out = tmp_path / "feeds-snap.tar.gz"
        assert backup_feeds(tmp_path / "does-not-exist", out) is False
        assert not out.exists()


class TestPrune:
    def test_keeps_newest(self, tmp_path: Path):
        for i in range(5):
            artifact = tmp_path / f"db-2026010{i}T000000Z.dump"
            artifact.write_text("x")
            # deterministic ordering via mtime
            import os

            os.utime(artifact, (i * 1000, i * 1000))
        pruned = prune_old_backups(tmp_path, "db-", keep=2)
        assert pruned == 3
        remaining = sorted(p.name for p in tmp_path.glob("db-*"))
        assert len(remaining) == 2

    def test_noop_when_under_limit(self, tmp_path: Path):
        (tmp_path / "db-a.dump").write_text("x")
        assert prune_old_backups(tmp_path, "db-", keep=5) == 0


class TestRunBackup:
    async def test_sqlite_database_is_skipped_gracefully(self, tmp_path: Path):
        result = await run_backup(backup_dir=tmp_path, keep=3)
        assert result["database_backup"] is None
        assert all(not e.startswith("database:") for e in result["errors"])

    async def test_pg_dump_failure_is_recorded(self, tmp_path: Path, monkeypatch):
        async def failing_dump(path):
            raise RuntimeError("pg_dump exploded")

        monkeypatch.setattr("omnisource.core.backup.run_database_backup", failing_dump)
        result = await run_backup(backup_dir=tmp_path, keep=3)
        assert any("pg_dump exploded" in e for e in result["errors"])
        assert result["ok"] is False

    async def test_result_shape(self, tmp_path: Path):
        feeds = tmp_path / "feeds"
        feeds.mkdir()
        (feeds / "all.json").write_text("{}")
        result = await run_backup(backup_dir=tmp_path, keep=3)
        assert set(result) == {"started_at", "database_backup", "feeds_backup", "errors", "ok"}
