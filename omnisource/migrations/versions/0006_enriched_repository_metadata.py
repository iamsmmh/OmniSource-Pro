"""Persist enriched repository metadata and extracted media references.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-11 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("changelog", sa.Text(), True),
    ("release_notes", sa.JSON(), False),
    ("languages", sa.JSON(), False),
    ("package_ecosystems", sa.JSON(), False),
    ("project_tags", sa.JSON(), False),
    ("enrichment", sa.JSON(), False),
    ("icon_url", sa.String(500), True),
    ("banner_url", sa.String(500), True),
    ("screenshot_urls", sa.JSON(), False),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "repository_metadata" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("repository_metadata")}
    for name, column_type, nullable in _COLUMNS:
        if name not in existing:
            default = (
                "[]"
                if name
                in {"release_notes", "package_ecosystems", "project_tags", "screenshot_urls"}
                else "{}"
            )
            op.add_column(
                "repository_metadata",
                sa.Column(
                    name,
                    column_type,
                    nullable=nullable,
                    server_default=None if nullable else default,
                ),
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "repository_metadata" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("repository_metadata")}
    for name, _, _ in reversed(_COLUMNS):
        if name in existing:
            op.drop_column("repository_metadata", name)
