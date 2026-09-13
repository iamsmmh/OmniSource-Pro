"""Add analytics event tables (download_events, view_events, search_events).

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ["download_events", "view_events", "search_events"]


def _table_exists(inspector: sa.Inspector, table: str) -> bool:
    try:
        return inspector.has_table(table)
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if all(_table_exists(inspector, table) for table in _TABLES):
        # Fresh database: 0001's create_all already built the tables.
        return
    from omnisource.core.models import Base

    for _table in ("download_events", "view_events", "search_events"):
        Base.metadata.tables[_table].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in reversed(_TABLES):
        if _table_exists(inspector, table):
            bind.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
