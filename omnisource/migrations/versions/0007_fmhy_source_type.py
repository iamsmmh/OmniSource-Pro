"""Register the fmhy source type on existing databases.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-12 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUM_NAME = "sourcetype"
_NEW_VALUE = "fmhy"


def upgrade() -> None:
    """Add the 'fmhy' value to the sources.source_type enum (PostgreSQL only).

    Fresh databases already contain the value because 0001 builds the schema
    from the current models via ``create_all``; only pre-existing enum types
    need the value appended. ``ALTER TYPE ... ADD VALUE`` cannot run inside a
    transaction that has performed other work, so it runs in an autocommit
    block.
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    exists = bind.execute(
        text("SELECT 1 FROM pg_type WHERE typname = :enum_name"),
        {"enum_name": _ENUM_NAME},
    )
    if exists.scalar_one_or_none() is None:
        return
    with op.get_context().autocommit_block():
        # DDL cannot bind identifiers; both fragments come from module constants.
        op.execute(f"ALTER TYPE {_ENUM_NAME} ADD VALUE IF NOT EXISTS '{_NEW_VALUE}'")


def downgrade() -> None:
    """PostgreSQL cannot remove enum values; downgrade is intentionally a no-op."""
