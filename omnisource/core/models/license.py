"""License models."""

from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base


class License(Base):
    """Represents a software license."""

    __tablename__ = "licenses"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    license_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    spdx_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    short_name: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(String(500))
    is_osi_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_fsf_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="license"
    )
