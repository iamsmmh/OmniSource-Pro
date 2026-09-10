"""
Initial database schema for OmniSource.

Revision ID: 0001
Revises: None
Create Date: 2026-09-07 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# Import all models
from omnisource.core.models import Base

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create initial tables."""
    # Create all tables from Base
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """Drop all tables."""
    # Drop all tables in reverse order
    Base.metadata.drop_all(bind=op.get_bind())
