"""Developer and organization models."""

from datetime import datetime, UTC
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base


class Developer(Base):
    """Represents a software developer or individual contributor."""

    __tablename__ = "developers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    developer_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    url: Mapped[Optional[str]] = mapped_column(String(500))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    bio: Mapped[Optional[str]] = mapped_column(Text)
    location: Mapped[Optional[str]] = mapped_column(String(255))

    # Relationships
    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="developer"
    )


class Organization(Base):
    """Represents an organization or company."""

    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    organization_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(String(500))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    location: Mapped[Optional[str]] = mapped_column(String(255))
    members_count: Mapped[Optional[int]] = mapped_column(Integer)

    # Relationships
    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="organization"
    )
