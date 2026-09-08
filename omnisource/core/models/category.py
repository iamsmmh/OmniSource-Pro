"""Category and tag models."""

from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnisource.core.models.base import Base


class CategoryType(str, Enum):
    """Standard category types for OmniSource."""

    AUDIO = "audio"
    VIDEO = "video"
    PHOTOGRAPHY = "photography"
    GRAPHICS = "graphics"
    PRODUCTIVITY = "productivity"
    DEVELOPER_TOOLS = "developer-tools"
    EDUCATION = "education"
    COMMUNICATION = "communication"
    SOCIAL = "social"
    INTERNET = "internet"
    BROWSERS = "browsers"
    SECURITY = "security"
    NETWORKING = "networking"
    UTILITIES = "utilities"
    GAMING = "gaming"
    BOOKS = "books"
    FINANCE = "finance"
    SCIENCE = "science"
    SYSTEM_TOOLS = "system-tools"
    AI = "ai"
    OTHER = "other"


# Standard taxonomy
TAXONOMY = {
    CategoryType.AUDIO: {"name": "Audio", "description": "Audio editing, recording, and playback applications"},
    CategoryType.VIDEO: {"name": "Video", "description": "Video editing, recording, and playback applications"},
    CategoryType.PHOTOGRAPHY: {"name": "Photography", "description": "Photo editing and management applications"},
    CategoryType.GRAPHICS: {"name": "Graphics", "description": "Graphic design and illustration applications"},
    CategoryType.PRODUCTIVITY: {"name": "Productivity", "description": "Productivity and office applications"},
    CategoryType.DEVELOPER_TOOLS: {"name": "Developer Tools", "description": "Development tools and IDEs"},
    CategoryType.EDUCATION: {"name": "Education", "description": "Educational applications"},
    CategoryType.COMMUNICATION: {"name": "Communication", "description": "Communication and messaging applications"},
    CategoryType.SOCIAL: {"name": "Social", "description": "Social media and networking applications"},
    CategoryType.INTERNET: {"name": "Internet", "description": "Internet and web applications"},
    CategoryType.BROWSERS: {"name": "Browsers", "description": "Web browsers"},
    CategoryType.SECURITY: {"name": "Security", "description": "Security and privacy applications"},
    CategoryType.NETWORKING: {"name": "Networking", "description": "Network tools and utilities"},
    CategoryType.UTILITIES: {"name": "Utilities", "description": "Utility applications"},
    CategoryType.GAMING: {"name": "Gaming", "description": "Games and gaming utilities"},
    CategoryType.BOOKS: {"name": "Books", "description": "E-book readers and literature applications"},
    CategoryType.FINANCE: {"name": "Finance", "description": "Financial and accounting applications"},
    CategoryType.SCIENCE: {"name": "Science", "description": "Scientific and mathematical applications"},
    CategoryType.SYSTEM_TOOLS: {"name": "System Tools", "description": "System utilities and tools"},
    CategoryType.AI: {"name": "AI", "description": "Artificial intelligence applications"},
    CategoryType.OTHER: {"name": "Other", "description": "Other applications"},
}


class Category(Base):
    """Represents an application category."""

    __tablename__ = "categories"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    category_type: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon: Mapped[Optional[str]] = mapped_column(String(100))
    parent_id: Mapped[Optional[UUID]] = mapped_column(
        foreign_key="categories.id", index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    applications: Mapped[list["Application"]] = relationship(
        "Application", secondary="application_categories", back_populates="categories"
    )
    parent: Mapped[Optional["Category"]] = relationship(
        "Category", remote_side=[id], backref="children"
    )


class Tag(Base):
    """Represents a tag for applications."""

    __tablename__ = "tags"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    applications: Mapped[list["Application"]] = relationship(
        "Application", secondary="application_tags", back_populates="tags"
    )
