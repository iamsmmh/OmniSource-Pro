"""Shared Gitea/Forgejo API client used by the Codeberg and Forgejo connectors.

Both platforms expose the Gitea HTTP API, so a single client serves them with
a different ``api_url``. Endpoints used:

- ``GET /version``                          → health check
- ``GET /repos/search``                     → repository discovery
- ``GET /repos/{owner}/{repo}``             → repository detail
- ``GET /repos/{owner}/{repo}/releases``    → releases with inline assets
- ``GET /repos/{owner}/{repo}/languages``   → language breakdown
- ``GET /repos/{owner}/{repo}/topics``      → topic list
"""

from datetime import datetime, timedelta
from typing import Any

import httpx

from omnisource.config.logging import get_logger
from omnisource.connectors.base import ConnectorError
from omnisource.connectors.rate_limiter import RateLimiter

logger = get_logger(__name__)

_USER_AGENT = "OmniSource/0.1.0"


class GiteaClient:
    """Minimal async client for Gitea-compatible APIs (Gitea, Forgejo)."""

    def __init__(
        self,
        api_url: str,
        token: str | None = None,
        rate_limiter: RateLimiter | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.rate_limiter = rate_limiter or RateLimiter(
            max_requests=1000, period=timedelta(minutes=1)
        )
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout

    async def initialize(self) -> None:
        headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        self._client = httpx.AsyncClient(
            base_url=self.api_url, headers=headers, timeout=self._timeout
        )
        logger.info("Gitea client initialized for %s", self.api_url)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if self._client is None:
            raise ConnectorError("Gitea client not initialized", is_retriable=False)
        await self.rate_limiter.wait_for_token()
        try:
            response = await self._client.get(path, params=params)
        except httpx.TimeoutException as e:
            raise ConnectorError(f"Timeout requesting {path}") from e
        except httpx.ConnectError as e:
            raise ConnectorError(f"Connection error requesting {path}") from e

        if response.status_code == 404:
            raise ConnectorError(f"Not found: {path}", error_code="HTTP_404")
        if response.status_code == 401:
            raise ConnectorError(
                "Authentication failed for Gitea API",
                error_code="AUTH_ERROR",
                is_retriable=False,
            )
        if response.status_code == 429 or response.status_code >= 500:
            raise ConnectorError(f"Gitea API error {response.status_code}", error_code="RATE_LIMIT")
        response.raise_for_status()
        return response.json()

    # --- Endpoints ---------------------------------------------------------

    async def version(self) -> dict[str, Any]:
        """Fetch server version; used for health checks."""
        return await self._get("/version")

    async def search_repositories(
        self,
        query: str | None = None,
        page: int = 1,
        limit: int = 50,
        sort: str = "updated",
        order: str = "desc",
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "page": page,
            "limit": min(limit, 50),  # Gitea caps at 50
            "sort": sort,
            "order": order,
        }
        if query:
            params["q"] = query
        data = await self._get("/repos/search", params=params)
        return data.get("data", []) if isinstance(data, dict) else list(data)

    async def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        return await self._get(f"/repos/{owner}/{repo}")

    async def get_releases(
        self, owner: str, repo: str, page: int = 1, limit: int = 20
    ) -> list[dict[str, Any]]:
        return await self._get(
            f"/repos/{owner}/{repo}/releases",
            params={"page": page, "limit": min(limit, 50)},
        )

    async def get_languages(self, owner: str, repo: str) -> dict[str, int]:
        return await self._get(f"/repos/{owner}/{repo}/languages")

    async def get_topics(self, owner: str, repo: str) -> list[str]:
        data = await self._get(f"/repos/{owner}/{repo}/topics")
        return data.get("topics", []) if isinstance(data, dict) else []


def parse_iso_datetime(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp as returned by Gitea APIs."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
