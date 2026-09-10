"""Breaking-change flags on releases + webhook_subscriptions table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_columns(inspector: sa.Inspector, table: str) -> set[str]:
    try:
        return {col["name"] for col in inspector.get_columns(table)}
    except Exception:
        return set()


def _existing_tables(inspector: sa.Inspector) -> set[str]:
    return set(inspector.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = _existing_tables(inspector)

    if "releases" in tables:
        existing = _existing_columns(inspector, "releases")
        if "has_breaking_changes" not in existing:
            op.add_column(
                "releases",
                sa.Column(
                    "has_breaking_changes", sa.Boolean(), nullable=False, server_default=sa.false()
                ),
            )
        if "breaking_signals" not in existing:
            op.add_column(
                "releases",
                sa.Column("breaking_signals", sa.JSON(), nullable=False, server_default="[]"),
            )

    if "webhook_subscriptions" not in tables:
        op.create_table(
            "webhook_subscriptions",
            sa.Column("id", sa.Uuid(), primary_key=True, index=True),
            sa.Column("url", sa.String(1000), nullable=False),
            sa.Column("events", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("secret", sa.String(255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("description", sa.String(500), nullable=True),
            sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_delivery_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_delivery_status", sa.String(20), nullable=True),
            sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = _existing_tables(inspector)

    if "webhook_subscriptions" in tables:
        op.drop_table("webhook_subscriptions")

    if "releases" in tables:
        existing = _existing_columns(inspector, "releases")
        if "breaking_signals" in existing:
            op.drop_column("releases", "breaking_signals")
        if "has_breaking_changes" in existing:
            op.drop_column("releases", "has_breaking_changes")
