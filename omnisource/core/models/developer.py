"""Developer and organization models."""

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base

if TYPE_CHECKING:
    # Resolved by SQLAlchemy relationship() at runtime; imported for type checkers only.
    from omnisource.core.models.application import Application


class Developer(Base):
    """Represents a software developer or individual contributor."""

    __tablename__ = "developers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    developer_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(500))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    bio: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(255))

    # Relationships
    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="developer"
    )


class Organization(Base):
    """Represents an organization or company."""

    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    organization_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(500))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(255))
    members_count: Mapped[int | None] = mapped_column(Integer)

    # Relationships
    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="organization"
    )
