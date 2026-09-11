"""Public DTOs for favorites, collections, and privacy-safe analytics."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from omnisource.core.schemas.omnistore import OmniStoreApp


class InteractionTypeSchema(str, Enum):
    VIEW = "view"
    INSTALL = "install"
    DOWNLOAD = "download"
    FAVORITE = "favorite"
    UNFAVORITE = "unfavorite"
    SEARCH = "search"


class FavoriteRequest(BaseModel):
    """Request to add or remove an application from the caller's favorites."""

    app_id: str = Field(min_length=1, max_length=255)


class FavoriteResponse(BaseModel):
    """A favorite application returned to the caller."""

    app: OmniStoreApp
    created_at: datetime | None = None


class PaginatedFavorites(BaseModel):
    """Paginated personal favorites response."""

    items: list[FavoriteResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    per_page: int = Field(ge=1)


class CollectionCreate(BaseModel):
    """Create a private or public collection."""

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    is_public: bool = False

    @field_validator("name")
    @classmethod
    def normalise_name(cls, value: str) -> str:
        return " ".join(value.split())


class CollectionItemRequest(BaseModel):
    """Request to add an app to a collection."""

    app_id: str = Field(min_length=1, max_length=255)
    sort_order: int = Field(default=0, ge=0, le=100000)


class CollectionResponse(BaseModel):
    """Collection summary or detail. Private ownership is never exposed."""

    id: str
    slug: str
    name: str
    description: str | None = None
    is_public: bool
    item_count: int = Field(ge=0)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    items: list[OmniStoreApp] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PaginatedCollections(BaseModel):
    """Paginated collection summaries."""

    items: list[CollectionResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    per_page: int = Field(ge=1)


class AnalyticsEventRequest(BaseModel):
    """An allowlisted interaction event from an authenticated OmniStore service."""

    event_type: InteractionTypeSchema
    app_id: str | None = Field(default=None, min_length=1, max_length=255)
    platform: str | None = Field(default=None, min_length=1, max_length=32)
    dimensions: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @field_validator("dimensions")
    @classmethod
    def bound_dimensions(
        cls, value: dict[str, str | int | float | bool]
    ) -> dict[str, str | int | float | bool]:
        if len(value) > 10:
            raise ValueError("at most 10 analytics dimensions are allowed")
        result: dict[str, str | int | float | bool] = {}
        for key, item in value.items():
            if not key or len(key) > 64:
                raise ValueError("analytics dimension keys must be 1-64 characters")
            if isinstance(item, str) and len(item) > 128:
                raise ValueError("analytics dimension values must be at most 128 characters")
            result[key] = item
        return result


class AnalyticsSummary(BaseModel):
    """Aggregate-only analytics response."""

    events: int = Field(ge=0)
    favorites: int = Field(ge=0)
    downloads: int = Field(ge=0)
    installs: int = Field(ge=0)
    views: int = Field(ge=0)
