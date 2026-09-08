"""Base model for SQLAlchemy."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(AsyncAttrs, DeclarativeBase):
    """Base model with common fields and methods."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    def __repr__(self) -> str:
        """String representation of the model."""
        attrs = []
        for column in self.__table__.columns:
            if column.name not in ("created_at", "updated_at"):
                attrs.append(f"{column.name}={getattr(self, column.name)!r}")
        return f"{self.__class__.__name__}({', '.join(attrs)})"

    def to_dict(self, exclude: set[str] | None = None) -> dict[str, Any]:
        """Convert model to dictionary."""
        exclude = exclude or set()
        exclude.update({"created_at", "updated_at", "is_deleted"})

        result = {}
        for column in self.__table__.columns:
            if column.name not in exclude:
                value = getattr(self, column.name)
                # Convert UUID to string
                if isinstance(value, UUID):
                    value = str(value)
                # Convert datetime to ISO format
                elif isinstance(value, datetime):
                    value = value.isoformat()
                result[column.name] = value
        return result


class UUIDModel(Base):
    """Base model with UUID primary key."""

    __abstract__ = True

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
