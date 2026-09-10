"""Stored embedding vectors for semantic search."""

from uuid import UUID, uuid4

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from omnisource.core.models.base import Base


class AppEmbedding(Base):
    """A stored embedding vector for an application.

    Kept intentionally simple (JSON column) so it works on SQLite and
    PostgreSQL alike; large deployments should move to pgvector.
    """

    __tablename__ = "app_embeddings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    embedding: Mapped[list | dict] = mapped_column(JSON, nullable=False)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["AppEmbedding"]
