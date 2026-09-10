"""Base feed schemas."""

from pydantic import BaseModel, Field

from omnisource.core.schemas.omnistore import OmniStoreApp


class FeedEnvelope(BaseModel):
    """Envelope wrapping a generated feed payload."""

    version: str = Field(..., description="Feed schema version")
    platform: str = Field(..., description="Target platform (or 'all')")
    generated_at: str = Field(..., description="Generation timestamp (ISO 8601)")
    total: int = Field(..., description="Number of applications in the feed")
    apps: list[OmniStoreApp] = Field(default_factory=list, description="Applications")
