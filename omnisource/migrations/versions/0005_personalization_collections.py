"""Add pseudonymous favorites, collections, and interaction aggregates.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-11 00:00:00.000000

The migration stores only an HMAC-derived subject identifier. Raw OmniStore
identity values are intentionally never persisted in this database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    if "user_favorites" not in existing:
        op.create_table(
            "user_favorites",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("subject_hash", sa.String(64), nullable=False, index=True),
            sa.Column(
                "application_id",
                sa.Uuid(),
                sa.ForeignKey("applications.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
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
            sa.UniqueConstraint(
                "subject_hash", "application_id", name="uq_user_favorites_subject_app"
            ),
        )
    if "collections" not in existing:
        op.create_table(
            "collections",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("subject_hash", sa.String(64), nullable=False, index=True),
            sa.Column("slug", sa.String(120), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "is_public", sa.Boolean(), nullable=False, server_default=sa.false(), index=True
            ),
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
            sa.UniqueConstraint("subject_hash", "slug", name="uq_collections_subject_slug"),
        )
    if "collection_items" not in existing:
        op.create_table(
            "collection_items",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "collection_id",
                sa.Uuid(),
                sa.ForeignKey("collections.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "application_id",
                sa.Uuid(),
                sa.ForeignKey("applications.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
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
            sa.UniqueConstraint("collection_id", "application_id", name="uq_collection_items_app"),
        )
    if "analytics_events" not in existing:
        op.create_table(
            "analytics_events",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("subject_hash", sa.String(64), nullable=True, index=True),
            sa.Column(
                "application_id",
                sa.Uuid(),
                sa.ForeignKey("applications.id", ondelete="CASCADE"),
                nullable=True,
                index=True,
            ),
            sa.Column(
                "event_type",
                sa.Enum(
                    "VIEW",
                    "INSTALL",
                    "DOWNLOAD",
                    "FAVORITE",
                    "UNFAVORITE",
                    "SEARCH",
                    name="interactiontype",
                ),
                nullable=False,
                index=True,
            ),
            sa.Column("platform", sa.String(32), nullable=True, index=True),
            sa.Column(
                "occurred_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
                index=True,
            ),
            sa.Column("dimensions", sa.JSON(), nullable=False, server_default="{}"),
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
    inspector = sa.inspect(op.get_bind())
    for table in ("analytics_events", "collection_items", "collections", "user_favorites"):
        if table in inspector.get_table_names():
            op.drop_table(table)
