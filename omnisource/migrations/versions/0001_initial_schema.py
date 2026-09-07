"""
Initial database schema for OmniSource.

Revision ID: 0001
Revises: None
Create Date: 2026-09-07 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Import all models
from omnisource.core.models import Base

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial tables."""
    # Create all tables from Base
    op.create_all(Base.metadata)


def downgrade() -> None:
    """Drop all tables."""
    # Drop all tables in reverse order
    op.drop_all(Base.metadata)
