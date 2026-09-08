"""Screenshot and icon models."""

from datetime import datetime, UTC
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base
from omnisource.core.models.application import Application
from omnisource.core.models.platform import Platform


class Screenshot(Base):
    """Represents a screenshot for an application."""

    __tablename__ = "screenshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    application_id: Mapped[UUID] = mapped_column(
        foreign_key="applications.id", nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500))
    cached_url: Mapped[Optional[str]] = mapped_column(String(500))
    caption: Mapped[Optional[str]] = mapped_column(String(500))
    alt_text: Mapped[Optional[str]] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    platform_id: Mapped[Optional[UUID]] = mapped_column(
        foreign_key="platforms.id", index=True
    )
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    validation_message: Mapped[Optional[str]] = mapped_column(String(500))

    # Relationships
    application: Mapped[Application] = relationship(
        "Application", back_populates="screenshots"
    )
    platform: Mapped[Optional[Platform]] = relationship(
        "Platform"
    )


class Icon(Base):
    """Represents an icon for an application."""

    __tablename__ = "icons"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    application_id: Mapped[UUID] = mapped_column(
        foreign_key="applications.id", nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    cached_url: Mapped[Optional[str]] = mapped_column(String(500))
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500))
    alt_text: Mapped[Optional[str]] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    validation_message: Mapped[Optional[str]] = mapped_column(String(500))
    background_color: Mapped[Optional[str]] = mapped_column(String(50))

    # Relationships
    application: Mapped[Application] = relationship(
        "Application", back_populates="icons"
    )
