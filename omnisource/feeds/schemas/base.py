"""Base feed schemas."""

from pydantic import BaseModel, Field

from omnisource.core.schemas.omnistore import OmniStoreApp


class FeedEnvelope(BaseModel):
    """Envelope wrapping a generated feed payload."""

    version: str = Field(..., description="Feed schema version")
    platform: str = Field(..., description="Target platform (or 'all')")
    generated_at: str = Field(..., description="Generation timestamp (ISO 8601)")
    total: int = Field(..., description="Number of applications in the feed")
    channel: str = Field(default="stable", description="Release channel")
    source_count: int = Field(default=0, ge=0, description="Distinct catalog sources represented")
    package_count: int = Field(default=0, ge=0, description="Number of packages/applications")
    sha256: str | None = Field(default=None, description="SHA-256 of the canonical unsigned feed")
    signature: str | None = Field(default=None, description="Base64 Ed25519 signature")
    signing_key: str | None = Field(default=None, description="Base64 Ed25519 public key")
    apps: list[OmniStoreApp] = Field(default_factory=list, description="Applications")
