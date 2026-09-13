"""Canonical DDL for the OmniSource catalogue views.

Four catalogue views back the hot ranking endpoints (trending, featured,
recently updated, most downloaded):

* ``mv_trending_apps`` — composite trending score:
  50% normalized popularity score (popularity_scores)
  + 30% download momentum (``download_count``, saturating at 500)
  + 20% freshness (``updated_at`` within the last 30 days)
* ``mv_featured_apps`` — curated, published, active apps
* ``mv_recently_updated_apps`` — active apps ordered by ``updated_at``
* ``mv_most_downloaded_apps`` — published, active apps by download count

On PostgreSQL the views are **materialized** (and refreshed periodically by
the scheduler, see ``omnisource.automation.scheduler``); on other dialects
(primarily SQLite in CI and local development) they are plain live views with
equivalent semantics.

The same DDL is consumed by:

* migration ``0008_application_optimizations`` (creating them on upgrade),
* the test suite (``tests/conftest.py`` recreates the schema per test).
"""

from __future__ import annotations

from collections.abc import Mapping

import sqlalchemy as sa

CATALOG_VIEW_NAMES: tuple[str, ...] = (
    "mv_trending_apps",
    "mv_featured_apps",
    "mv_recently_updated_apps",
    "mv_most_downloaded_apps",
)

_PG_TRENDING = """
CREATE MATERIALIZED VIEW mv_trending_apps AS
SELECT a.id,
       a.app_id,
       a.slug,
       a.name,
       a.short_description,
       a.bundle_id,
       a.download_count,
       a.updated_at,
       COALESCE(ps.normalized_score, 0) AS popularity_score,
       (0.5 * COALESCE(ps.normalized_score, 0)
        + 0.3 * (100.0 * LEAST(1.0, a.download_count::float / 500.0))
        + 0.2 * (100.0 * GREATEST(
              0.0,
              1.0 - (EXTRACT(EPOCH FROM (now() - a.updated_at)) / 86400.0) / 30.0
          ))) AS trending_score
FROM applications a
LEFT JOIN popularity_scores ps ON ps.application_id = a.id
WHERE a.is_active AND a.status = 'PUBLISHED' AND NOT a.is_deleted
"""

_SQLITE_TRENDING = """
CREATE VIEW mv_trending_apps AS
SELECT a.id,
       a.app_id,
       a.slug,
       a.name,
       a.short_description,
       a.bundle_id,
       a.download_count,
       a.updated_at,
       COALESCE(ps.normalized_score, 0) AS popularity_score,
       (0.5 * COALESCE(ps.normalized_score, 0)
        + 0.3 * (100.0 * MIN(1.0, a.download_count / 500.0))
        + 0.2 * (100.0 * MAX(
              0.0,
              1.0 - (strftime('%s', 'now') - strftime('%s', a.updated_at)) / 2592000.0
          ))) AS trending_score
FROM applications a
LEFT JOIN popularity_scores ps ON ps.application_id = a.id
WHERE a.is_active = 1 AND a.status = 'PUBLISHED' AND a.is_deleted = 0
"""

_PG_FEATURED = """
CREATE MATERIALIZED VIEW mv_featured_apps AS
SELECT a.id, a.app_id, a.slug, a.name, a.short_description, a.bundle_id,
       a.download_count, a.updated_at
FROM applications a
WHERE a.is_featured AND a.is_active AND a.status = 'PUBLISHED' AND NOT a.is_deleted
"""

_SQLITE_FEATURED = """
CREATE VIEW mv_featured_apps AS
SELECT a.id, a.app_id, a.slug, a.name, a.short_description, a.bundle_id,
       a.download_count, a.updated_at
FROM applications a
WHERE a.is_featured = 1 AND a.is_active = 1 AND a.status = 'PUBLISHED'
  AND a.is_deleted = 0
"""

_PG_RECENT = """
CREATE MATERIALIZED VIEW mv_recently_updated_apps AS
SELECT a.id, a.app_id, a.slug, a.name, a.short_description, a.bundle_id,
       a.updated_at
FROM applications a
WHERE a.is_active AND NOT a.is_deleted
ORDER BY a.updated_at DESC
"""

_SQLITE_RECENT = """
CREATE VIEW mv_recently_updated_apps AS
SELECT a.id, a.app_id, a.slug, a.name, a.short_description, a.bundle_id,
       a.updated_at
FROM applications a
WHERE a.is_active = 1 AND a.is_deleted = 0
ORDER BY a.updated_at DESC
"""

_PG_MOST_DOWNLOADED = """
CREATE MATERIALIZED VIEW mv_most_downloaded_apps AS
SELECT a.id, a.app_id, a.slug, a.name, a.short_description, a.bundle_id,
       a.download_count, a.updated_at
FROM applications a
WHERE a.is_active AND a.status = 'PUBLISHED' AND NOT a.is_deleted
ORDER BY a.download_count DESC, a.updated_at DESC
"""

_SQLITE_MOST_DOWNLOADED = """
CREATE VIEW mv_most_downloaded_apps AS
SELECT a.id, a.app_id, a.slug, a.name, a.short_description, a.bundle_id,
       a.download_count, a.updated_at
FROM applications a
WHERE a.is_active = 1 AND a.status = 'PUBLISHED' AND a.is_deleted = 0
ORDER BY a.download_count DESC, a.updated_at DESC
"""

CATALOG_VIEWS: Mapping[str, Mapping[str, str]] = {
    "postgresql": {
        "mv_trending_apps": _PG_TRENDING,
        "mv_featured_apps": _PG_FEATURED,
        "mv_recently_updated_apps": _PG_RECENT,
        "mv_most_downloaded_apps": _PG_MOST_DOWNLOADED,
    },
    "sqlite": {
        "mv_trending_apps": _SQLITE_TRENDING,
        "mv_featured_apps": _SQLITE_FEATURED,
        "mv_recently_updated_apps": _SQLITE_RECENT,
        "mv_most_downloaded_apps": _SQLITE_MOST_DOWNLOADED,
    },
}


def existing_catalog_views(bind: sa.engine.Connection) -> set[str]:
    """Names of both plain views and materialized views on this database."""
    if bind.dialect.name == "postgresql":
        rows = bind.execute(
            sa.text(
                "SELECT viewname FROM pg_views WHERE schemaname = 'public' "
                "UNION SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'"
            )
        ).fetchall()
    else:
        rows = bind.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type = 'view'")
        ).fetchall()
    return {str(row[0]) for row in rows}


def is_materialized_view(bind: sa.engine.Connection, view_name: str) -> bool:
    if bind.dialect.name != "postgresql":
        return False
    row = bind.execute(
        sa.text("SELECT 1 FROM pg_matviews WHERE schemaname = 'public' AND matviewname = :n"),
        {"n": view_name},
    ).fetchone()
    return row is not None


def drop_catalog_view(bind: sa.engine.Connection, view_name: str) -> None:
    """Drop a single catalogue view (plain or materialized), if present."""
    if not existing_catalog_views(bind) & {view_name}:
        return
    if is_materialized_view(bind, view_name):
        bind.execute(sa.text(f"DROP MATERIALIZED VIEW IF EXISTS {view_name}"))
        # The unique index backing CONCURRENTLY refresh goes with the matview,
        # but drop it defensively as well.
        bind.execute(sa.text(f"DROP INDEX IF EXISTS uq_{view_name}_app_id"))
    else:
        bind.execute(sa.text(f"DROP VIEW IF EXISTS {view_name}"))


def create_catalog_view(bind: sa.engine.Connection, view_name: str) -> None:
    """Create a single catalogue view for the bound dialect (idempotent)."""
    dialect = bind.dialect.name
    definitions = CATALOG_VIEWS.get(dialect)
    if definitions is None or view_name not in definitions:
        raise RuntimeError(f"No catalogue view DDL for {view_name!r} on {dialect!r}")
    drop_catalog_view(bind, view_name)
    bind.execute(sa.text(definitions[view_name]))
    if dialect == "postgresql":
        # Unique index on app_id enables REFRESH MATERIALIZED ... CONCURRENTLY.
        bind.execute(sa.text(f"CREATE UNIQUE INDEX uq_{view_name}_app_id ON {view_name} (app_id)"))


def create_catalog_views(bind: sa.engine.Connection, refresh: bool = False) -> None:
    """(Re)create every catalogue view for the bound dialect.

    ``refresh=True`` also issues an initial ``REFRESH MATERIALIZED VIEW`` on
    PostgreSQL so the views are never empty right after creation.
    """
    dialect = bind.dialect.name
    definitions = CATALOG_VIEWS.get(dialect)
    if definitions is None:
        raise RuntimeError(f"Unsupported dialect for catalogue views: {dialect}")
    for view_name in definitions:
        create_catalog_view(bind, view_name)
    if dialect == "postgresql" and refresh:
        for view_name in definitions:
            bind.execute(sa.text(f"REFRESH MATERIALIZED VIEW {view_name}"))


def drop_catalog_views(bind: sa.engine.Connection) -> None:
    """Drop every catalogue view that exists on the bound database."""
    for view_name in CATALOG_VIEW_NAMES:
        drop_catalog_view(bind, view_name)


def ensure_catalog_views(bind: sa.engine.Connection) -> None:
    """Create any missing catalogue view (idempotent, never drops).

    Used by application startup so a database that has only had its tables
    created (without the migration chain) still serves the catalogue views.
    On PostgreSQL the views are refreshed once after creation.
    """
    dialect = bind.dialect.name
    definitions = CATALOG_VIEWS.get(dialect)
    if definitions is None:
        return  # dialect without catalogue views (e.g. in-memory tests)
    existing = existing_catalog_views(bind)
    created = False
    for view_name in definitions:
        if view_name not in existing:
            create_catalog_view(bind, view_name)
            created = True
    if dialect == "postgresql" and created:
        for view_name in definitions:
            bind.execute(sa.text(f"REFRESH MATERIALIZED VIEW {view_name}"))
