"""Base model for SQLAlchemy."""

from datetime import datetime, UTC
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    """Base model with common fields and methods."""

    @declared_attr
    def __tablename__(cls) -> str:
        """Generate table name from class name."""
        return cls.__name__.lower()

    id: Any = None  # Will be overridden by subclasses

    @declared_attr
    def created_at(cls) -> Any:
        """Created timestamp."""
        return DateTime(timezone=True, server_default=func.now(UTC), nullable=False)

    @declared_attr
    def updated_at(cls) -> Any:
        """Updated timestamp."""
        return DateTime(
            timezone=True,
            server_default=func.now(UTC),
            onupdate=func.now(UTC),
            nullable=False,
        )

    @declared_attr
    def is_deleted(cls) -> Any:
        """Soft delete flag."""
        from sqlalchemy import Boolean
        return Boolean(default=False, nullable=False)

    def __repr__(self) -> str:
        """String representation of the model."""
        attrs = []
        for column in self.__table__.columns:
            if column.name != "created_at" and column.name != "updated_at":
                attrs.append(f"{column.name}={getattr(self, column.name)!r}")
        return f"{self.__class__.__name__}({', '.join(attrs)})"

    def to_dict(self, exclude: set[str] | None = None) -> dict[str, Any]:
        """Convert model to dictionary."""
        exclude = exclude or set()
        exclude.add("created_at")
        exclude.add("updated_at")
        exclude.add("is_deleted")
        
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

    id = Any  # Will be overridden with UUID type
