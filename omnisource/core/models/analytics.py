"""Analytics event models.

Privacy model: events are pseudonymous at most. ``subject_hash`` is the HMAC
of an upstream OmniStore subject (never the raw subject) and is optional;
``country`` is a two-letter ISO code derived from the client IP by the
ingesting client, not a precise location.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from omnisource.core.models.base import Base


class _AnalyticsEvent(Base):
    """Shared shape for the three analytics event tables."""

    __abstract__ = True

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subject_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    platform: Mapped[str | None] = mapped_column(String(40), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    client_info: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class DownloadEvent(_AnalyticsEvent):
    """A recorded application download."""

    __tablename__ = "download_events"
    __table_args__ = (Index("ix_download_events_app_time", "application_id", "occurred_at"),)


class ViewEvent(_AnalyticsEvent):
    """A recorded application detail-page view."""

    __tablename__ = "view_events"
    __table_args__ = (Index("ix_view_events_app_time", "application_id", "occurred_at"),)


class SearchEvent(_AnalyticsEvent):
    """A recorded search query (``query_text`` normalized to lowercase)."""

    __tablename__ = "search_events"

    query_text: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    results_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    took_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (Index("ix_search_events_time", "occurred_at"),)


__all__ = ["DownloadEvent", "SearchEvent", "ViewEvent"]
