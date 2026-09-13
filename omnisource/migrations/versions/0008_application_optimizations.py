"""Application optimization: dedup/lookup columns, indexes, materialized views.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-12 00:00:00.000000

Adds:
* ``applications.bundle_id``    - stable package identifier, cross-source dedup key
* ``applications.category_id``  - primary category FK
* ``applications.download_count`` - cumulative download counter
* indexes on bundle_id, category_id, updated_at, download_count (``slug`` is
  already uniquely indexed)
* catalogue views (materialized on PostgreSQL, plain on other dialects such as
  the SQLite used by CI) - definitions live in
  ``omnisource.core.database.catalog_views``:
  - mv_trending_apps
  - mv_featured_apps
  - mv_recently_updated_apps
  - mv_most_downloaded_apps

Fresh databases already contain the columns and indexes because 0001 builds
the schema from the current models; every statement below is guarded by
inspector checks so the same chain works on both paths.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from omnisource.core.database.catalog_views import (
    CATALOG_VIEWS,
    create_catalog_view,
    drop_catalog_view,
    existing_catalog_views,
)

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "applications"

_NEW_COLUMNS: list[tuple[str, sa.types.TypeEngine, bool]] = [
    ("bundle_id", sa.String(length=255), True),
    ("category_id", sa.Uuid(), True),
    ("download_count", sa.Integer(), False),
]

# (index_name, columns). bundle_id/category_id/download_count indexes also
# exist from create_all on fresh databases; the checks keep both paths safe.
_NEW_INDEXES = [
    ("ix_applications_bundle_id", ["bundle_id"]),
    ("ix_applications_category_id", ["category_id"]),
    ("ix_applications_updated_at", ["updated_at"]),
    ("ix_applications_download_count", ["download_count"]),
]


def _existing_columns(inspector: sa.Inspector, table: str) -> set[str]:
    try:
        return {col["name"] for col in inspector.get_columns(table)}
    except Exception:
        return set()


def _existing_indexes(inspector: sa.Inspector, table: str) -> set[str]:
    try:
        return {str(idx["name"]) for idx in inspector.get_indexes(table) if idx["name"] is not None}
    except Exception:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect = bind.dialect.name

    # 1. Columns -----------------------------------------------------------------
    existing = _existing_columns(inspector, _TABLE)
    if existing:  # empty result means the table is missing entirely
        for name, column_type, nullable in _NEW_COLUMNS:
            if name not in existing:
                op.add_column(_TABLE, sa.Column(name, column_type, nullable=nullable))
        # Backfill safety: ensure the counter is never NULL.
        bind.execute(
            sa.text("UPDATE applications SET download_count = 0 WHERE download_count IS NULL")
        )

        # 2. Foreign key for category_id. PostgreSQL can attach it cheaply;
        #    SQLite would require a table rebuild, so fresh SQLite databases get
        #    the FK from create_all and pre-existing ones stay unconstrained.
        if dialect == "postgresql" and "category_id" in existing:
            fk_exists = bind.execute(
                sa.text(
                    "SELECT 1 FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "WHERE t.relname = 'applications' "
                    "AND c.conname = 'fk_applications_category_id'"
                )
            ).fetchone()
            if fk_exists is None:
                op.create_foreign_key(
                    "fk_applications_category_id",
                    _TABLE,
                    "categories",
                    ["category_id"],
                    ["id"],
                    ondelete="SET NULL",
                )

    # 3. Indexes -----------------------------------------------------------------
    indexes = _existing_indexes(inspector, _TABLE)
    for name, columns in _NEW_INDEXES:
        if name not in indexes:
            op.create_index(name, table_name=_TABLE, columns=columns, unique=False)

    # 4. Views -------------------------------------------------------------------
    if dialect not in CATALOG_VIEWS:
        raise RuntimeError(f"Unsupported dialect for catalogue views: {dialect}")
    views = existing_catalog_views(bind)
    for view_name in CATALOG_VIEWS[dialect]:
        if view_name not in views:
            create_catalog_view(bind, view_name)

    # 5. Initial refresh on PostgreSQL so the views are never empty after a
    #    fresh deploy.
    if dialect == "postgresql":
        for view_name in CATALOG_VIEWS["postgresql"]:
            bind.execute(sa.text(f"REFRESH MATERIALIZED VIEW {view_name}"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect = bind.dialect.name

    # Views must go before the columns they reference.
    for view_name in CATALOG_VIEWS.get(dialect, {}):
        drop_catalog_view(bind, view_name)

    indexes = _existing_indexes(inspector, _TABLE)
    for name, _columns in _NEW_INDEXES:
        if name in indexes:
            op.drop_index(name, table_name=_TABLE)

    existing = _existing_columns(inspector, _TABLE)
    for name, _column_type, _nullable in _NEW_COLUMNS:
        if name in existing:
            op.drop_column(_TABLE, name)
