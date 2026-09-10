"""Add delta-sync tracking columns to repositories.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_COLUMNS = [
    ("last_synced_pushed_at", sa.DateTime(timezone=True), True),
    ("synced_at", sa.DateTime(timezone=True), True),
]


def _existing_columns(inspector: sa.Inspector, table: str) -> set[str]:
    try:
        return {col["name"] for col in inspector.get_columns(table)}
    except Exception:
        return set()


def upgrade() -> None:
    """Add delta-sync columns when the table predates them."""
    inspector = sa.inspect(op.get_bind())
    existing = _existing_columns(inspector, "repositories")
    if not existing:
        # Fresh database: 0001's create_all already included the new columns.
        return
    for name, column_type, nullable in _NEW_COLUMNS:
        if name not in existing:
            op.add_column("repositories", sa.Column(name, column_type, nullable=nullable))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = _existing_columns(inspector, "repositories")
    for name, _, _ in reversed(_NEW_COLUMNS):
        if name in existing:
            op.drop_column("repositories", name)
