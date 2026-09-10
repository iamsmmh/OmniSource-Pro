"""License models."""

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base

if TYPE_CHECKING:
    # Resolved by SQLAlchemy relationship() at runtime; imported for type checkers only.
    from omnisource.core.models.application import Application


class License(Base):
    """Represents a software license."""

    __tablename__ = "licenses"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    license_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    spdx_id: Mapped[str | None] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    short_name: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(500))
    is_osi_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_fsf_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="license"
    )
