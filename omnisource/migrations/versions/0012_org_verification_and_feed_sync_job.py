"""Organization verification columns and the feed_sync job type.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ORG_COLUMNS = [
    ("is_verified", sa.Boolean(), False),
    ("verified_at", sa.DateTime(timezone=True), True),
]


def _existing_columns(inspector: sa.Inspector, table: str) -> set[str]:
    try:
        return {col["name"] for col in inspector.get_columns(table)}
    except Exception:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. organizations.is_verified / verified_at
    existing = _existing_columns(inspector, "organizations")
    if existing:
        if "is_verified" not in existing:
            op.add_column(
                "organizations",
                sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
            )
        if "verified_at" not in existing:
            op.add_column(
                "organizations",
                sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            )

    # 2. sync job type enum: add 'feed_sync' (PostgreSQL only).
    if bind.dialect.name == "postgresql":
        exists = bind.execute(
            sa.text("SELECT 1 FROM pg_type WHERE typname = 'syncjobtype'")
        ).fetchone()
        if exists is not None:
            with op.get_context().autocommit_block():
                bind.execute(sa.text("ALTER TYPE syncjobtype ADD VALUE IF NOT EXISTS 'FEED_SYNC'"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # PostgreSQL cannot remove enum values; downgrade only drops the columns.
    existing = _existing_columns(inspector, "organizations")
    for name, _type, _nullable in reversed(_ORG_COLUMNS):
        if name in existing:
            op.drop_column("organizations", name)
