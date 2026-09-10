"""
Base connector class for OmniSource.

All source connectors should inherit from this class and implement the required methods.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel, Field

from omnisource.core.schemas.asset import AssetSchema
from omnisource.core.schemas.release import ReleaseSchema
from omnisource.core.schemas.repository import RepositorySchema


class ConnectorError(Exception):
    """Base exception for connector errors."""

    def __init__(self, message: str, error_code: str | None = None, is_retriable: bool = True):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.is_retriable = is_retriable


class RateLimitError(ConnectorError):
    """Rate limit exceeded error."""

    def __init__(self, reset_at: datetime | None = None, remaining: int = 0):
        super().__init__(
            f"Rate limit exceeded. Remaining: {remaining}",
            error_code="RATE_LIMIT",
            is_retriable=True,
        )
        self.reset_at = reset_at
        self.remaining = remaining


class AuthError(ConnectorError):
    """Authentication error."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, error_code="AUTH_ERROR", is_retriable=False)


class NetworkError(ConnectorError):
    """Network error."""

    def __init__(self, message: str = "Network error"):
        super().__init__(message, error_code="NETWORK_ERROR", is_retriable=True)


class ParserError(ConnectorError):
    """Parser error."""

    def __init__(self, message: str = "Failed to parse response"):
        super().__init__(message, error_code="PARSER_ERROR", is_retriable=False)


class ConnectorHealth(BaseModel):
    """Health status of a connector."""

    source: str = Field(..., description="Source name")
    healthy: bool = Field(..., description="Is the connector healthy")
    latency_ms: float | None = Field(default=None, description="Average latency in ms")
    error_rate: float = Field(default=0.0, description="Error rate (0-1)")
    last_check: datetime | None = Field(default=None, description="Last health check timestamp")
    last_success: datetime | None = Field(default=None, description="Last successful request")
    last_error: str | None = Field(default=None, description="Last error message")


class ConnectorStats(BaseModel):
    """Statistics for a connector."""

    source: str = Field(..., description="Source name")
    requests: int = Field(default=0, description="Total requests")
    successes: int = Field(default=0, description="Successful requests")
    failures: int = Field(default=0, description="Failed requests")
    rate_limited: int = Field(default=0, description="Rate limited requests")
    repositories_discovered: int = Field(default=0, description="Repositories discovered")
    releases_discovered: int = Field(default=0, description="Releases discovered")
    assets_discovered: int = Field(default=0, description="Assets discovered")


T = TypeVar("T")


class PageInfo(BaseModel):
    """Pagination information."""

    page: int = Field(default=1, ge=1, description="Current page")
    per_page: int = Field(default=30, ge=1, le=100, description="Items per page")
    total: int = Field(default=0, description="Total items")
    total_pages: int = Field(default=0, description="Total pages")
    has_next: bool = Field(default=False, description="Has next page")
    has_previous: bool = Field(default=False, description="Has previous page")
    next_cursor: str | None = Field(default=None, description="Cursor for next page")
    prev_cursor: str | None = Field(default=None, description="Cursor for previous page")


class SourceConnector(ABC):
    """
    Abstract base class for source connectors.

    All connectors must implement the following methods:
    - discover: Discover repositories
    - get_repository: Get repository details
    - get_releases: Get repository releases
    - get_assets: Get release assets
    - get_metadata: Get repository metadata
    - health_check: Check connector health
    """

    source_name: str = ""
    source_type: str = ""
    base_url: str = ""
    api_url: str = ""

    def __init__(self, **kwargs: Any):
        """Initialize the connector."""
        self._initialized = False
        self._stats = ConnectorStats(source=self.source_name)
        self._health = ConnectorHealth(source=self.source_name, healthy=False)

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the connector (e.g., set up HTTP client)."""
        self._initialized = True

    @abstractmethod
    async def close(self) -> None:
        """Close the connector and clean up resources."""
        self._initialized = False

    @abstractmethod
    async def discover(
        self, query: str | None = None, cursor: str | None = None, limit: int = 100, **kwargs: Any
    ) -> tuple[list[RepositorySchema], PageInfo]:
        """
        Discover repositories from the source.

        Args:
            query: Optional search query
            cursor: Pagination cursor
            limit: Maximum number of repositories to return
            **kwargs: Additional parameters

        Returns:
            Tuple of (repositories, page_info)
        """
        pass

    @abstractmethod
    async def get_repository(self, repository_id: str, **kwargs: Any) -> RepositorySchema:
        """
        Get details for a specific repository.

        Args:
            repository_id: Repository identifier
            **kwargs: Additional parameters

        Returns:
            Repository schema
        """
        pass

    @abstractmethod
    async def get_releases(
        self, repository: RepositorySchema, **kwargs: Any
    ) -> list[ReleaseSchema]:
        """
        Get releases for a repository.

        Args:
            repository: Repository schema
            **kwargs: Additional parameters

        Returns:
            List of release schemas
        """
        pass

    @abstractmethod
    async def get_assets(self, release: ReleaseSchema, **kwargs: Any) -> list[AssetSchema]:
        """
        Get assets for a release.

        Args:
            release: Release schema
            **kwargs: Additional parameters

        Returns:
            List of asset schemas
        """
        pass

    @abstractmethod
    async def get_metadata(self, repository: RepositorySchema, **kwargs: Any) -> dict[str, Any]:
        """
        Get metadata for a repository.

        Args:
            repository: Repository schema
            **kwargs: Additional parameters

        Returns:
            Metadata dictionary
        """
        pass

    @abstractmethod
    async def health_check(self) -> ConnectorHealth:
        """
        Check the health of the connector.

        Returns:
            Health status
        """
        pass

    def get_stats(self) -> ConnectorStats:
        """Get connector statistics."""
        return self._stats

    def get_health(self) -> ConnectorHealth:
        """Get connector health status."""
        return self._health

    def update_stats(self, **kwargs: Any) -> None:
        """Update connector statistics."""
        for key, value in kwargs.items():
            if hasattr(self._stats, key):
                setattr(self._stats, key, value)

    def update_health(self, **kwargs: Any) -> None:
        """Update connector health."""
        for key, value in kwargs.items():
            if hasattr(self._health, key):
                setattr(self._health, key, value)

    @property
    def is_initialized(self) -> bool:
        """Check if connector is initialized."""
        return self._initialized
