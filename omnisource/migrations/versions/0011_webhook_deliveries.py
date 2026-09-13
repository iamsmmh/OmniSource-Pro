"""Add the webhook_deliveries audit/retry queue table.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "webhook_deliveries"


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
    from omnisource.core.models import Base

    Base.metadata.tables["webhook_deliveries"].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _table_exists(inspector, _TABLE):
        bind.execute(sa.text(f"DROP TABLE IF EXISTS {_TABLE}"))
