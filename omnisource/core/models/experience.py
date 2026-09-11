"""Personalization, collection, and aggregate-interaction persistence models.

User identifiers are never stored directly.  API routes transform an upstream
OmniStore subject into an HMAC-derived ``subject_hash`` before creating any of
these records.  That keeps this service from becoming a second identity store.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base

if TYPE_CHECKING:
    from omnisource.core.models.application import Application


class InteractionType(str, Enum):
    """Privacy-preserving events that can influence aggregate recommendations."""

    VIEW = "view"
    INSTALL = "install"
    DOWNLOAD = "download"
    FAVORITE = "favorite"
    UNFAVORITE = "unfavorite"
    SEARCH = "search"


class UserFavorite(Base):
    """A saved application for an opaque, HMAC-derived OmniStore subject."""

    __tablename__ = "user_favorites"
    __table_args__ = (
        UniqueConstraint("subject_hash", "application_id", name="uq_user_favorites_subject_app"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )

    application: Mapped["Application"] = relationship("Application")


class Collection(Base):
    """A named private collection belonging to one OmniStore subject."""

    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("subject_hash", "slug", name="uq_collections_subject_slug"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)

    items: Mapped[list["CollectionItem"]] = relationship(
        "CollectionItem", back_populates="collection", cascade="all, delete-orphan"
    )


class CollectionItem(Base):
    """An application saved in a collection."""

    __tablename__ = "collection_items"
    __table_args__ = (
        UniqueConstraint("collection_id", "application_id", name="uq_collection_items_app"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    collection_id: Mapped[UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    collection: Mapped[Collection] = relationship("Collection", back_populates="items")
    application: Mapped["Application"] = relationship("Application")


class AnalyticsEvent(Base):
    """A minimal, pseudonymous interaction signal used for aggregates only.

    No IP address, user agent, raw user ID, or free-form payload is retained.
    The optional dimensions are intentionally bounded by API validation.
    """

    __tablename__ = "analytics_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    subject_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[InteractionType] = mapped_column(
        SQLEnum(InteractionType), nullable=False, index=True
    )
    platform: Mapped[str | None] = mapped_column(String(32), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(UTC), nullable=False, index=True
    )
    dimensions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    application: Mapped["Application | None"] = relationship("Application")


__all__ = [
    "AnalyticsEvent",
    "Collection",
    "CollectionItem",
    "InteractionType",
    "UserFavorite",
]
