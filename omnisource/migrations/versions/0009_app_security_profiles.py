"""Add the app_security_profiles trust table.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "app_security_profiles"


def _table_exists(inspector: sa.Inspector, table: str) -> bool:
    try:
        return inspector.has_table(table)
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _table_exists(inspector, _TABLE):
        # Fresh database: 0001's create_all already built the table.
        return
    # Pre-existing database: build the table from the model definition so the
    # schema (columns, FK, enum, indexes) is byte-identical to fresh installs.
    from omnisource.core.models import Base

    Base.metadata.tables["app_security_profiles"].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _table_exists(inspector, _TABLE):
        bind.execute(sa.text(f"DROP TABLE IF EXISTS {_TABLE}"))
