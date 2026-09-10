"""Add app_embeddings table for semantic search.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "app_embeddings" in inspector.get_table_names():
        return
    op.create_table(
        "app_embeddings",
        sa.Column("id", sa.Uuid(), primary_key=True, index=True),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("model", sa.String(100), nullable=False, server_default=""),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "app_embeddings" in inspector.get_table_names():
        op.drop_table("app_embeddings")
