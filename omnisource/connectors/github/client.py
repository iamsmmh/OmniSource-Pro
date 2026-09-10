"""
GitHub API client for OmniSource.

Provides async HTTP client with rate limiting, retry, and caching.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import httpx
from httpx import AsyncClient, Response
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings
from omnisource.connectors.base import (
    AuthError,
    ConnectorError,
    NetworkError,
    RateLimitError,
)
from omnisource.connectors.cache import ResponseCache
from omnisource.connectors.rate_limiter import RateLimiter

logger = get_logger(__name__)


class GitHubClient:
    """
    Async GitHub API client with rate limiting, retry, and caching.

    Features:
    - Automatic token authentication
    - Rate limit awareness and waiting
    - Exponential backoff retry
    - Response caching
    - ETag/If-None-Match support
    - Pagination support
    """

    BASE_URL = "https://api.github.com"
    USER_AGENT = "OmniSource/0.1.0"

    def __init__(
        self,
        token: str | None = None,
        rate_limiter: RateLimiter | None = None,
        cache: ResponseCache | None = None,
        timeout: float = 30.0,
        retry_count: int = 3,
    ):
        """
        Initialize the GitHub client.

        Args:
            token: GitHub personal access token
            rate_limiter: Rate limiter instance
            cache: Response cache instance
            timeout: Request timeout in seconds
            retry_count: Maximum retry attempts
        """
        self.token = token or get_settings().github.GH_TOKEN
        self.rate_limiter = rate_limiter or RateLimiter(
            max_requests=get_settings().github.GH_RATE_LIMIT, period=timedelta(hours=1)
        )
        self.cache = cache or ResponseCache()
        self.timeout = timeout
        self.retry_count = retry_count
        self._client: AsyncClient | None = None
        self._headers = self._build_headers()

    def _build_headers(self) -> dict[str, str]:
        """Build default headers."""
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def initialize(self) -> None:
        """Initialize the HTTP client."""
        if self._client is None:
            self._client = AsyncClient(
                base_url=self.BASE_URL,
                headers=self._headers,
                timeout=self.timeout,
                follow_redirects=True,
            )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @asynccontextmanager
    async def session(self) -> Any:
        """Context manager for client session."""
        await self.initialize()
        try:
            yield self._client
        finally:
            await self.close()

    async def _make_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        etag: str | None = None,
        use_cache: bool = True,
        use_rate_limit: bool = True,
    ) -> Response:
        """
        Make an HTTP request with retry, rate limiting, and caching.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path
            params: Query parameters
            data: Form data
            json: JSON data
            headers: Additional headers
            etag: ETag for If-None-Match
            use_cache: Whether to use caching
            use_rate_limit: Whether to use rate limiting

        Returns:
            HTTP response

        Raises:
            RateLimitError: If rate limited
            AuthError: If authentication fails
            NetworkError: If network error occurs
            ConnectorError: For other errors
        """
        await self.initialize()

        url = urljoin(self.BASE_URL, path)

        # Add ETag header if provided
        request_headers = dict(self._headers)
        if headers:
            request_headers.update(headers)
        if etag:
            request_headers["If-None-Match"] = etag

        # Check rate limit before request
        if use_rate_limit:
            await self.rate_limiter.wait_for_token()

        # Check cache first
        cache_key = self._build_cache_key(method, path, params, data, json)
        if use_cache and cache_key:
            cached_response = self.cache.get(cache_key)
            if cached_response is not None:
                logger.debug(f"Cache hit for {method} {path}")
                return cached_response

        # Make the request with retry
        try:
            response = await self._retry_request(method, url, params, data, json, request_headers)
        except RetryError as e:
            last_exception = e.last_attempt.exception()
            if isinstance(last_exception, httpx.HTTPStatusError):
                status_code = last_exception.response.status_code
                if status_code in {401, 403}:
                    raise AuthError("GitHub authentication failed") from e
                elif status_code == 403 and "rate limit" in str(last_exception).lower():
                    raise RateLimitError() from e
                elif status_code == 429:
                    raise RateLimitError() from e
            raise NetworkError(f"Request failed after {self.retry_count} attempts: {e}") from e
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code in {401, 403}:
                raise AuthError("GitHub authentication failed") from e
            elif status_code == 403 and "rate limit" in str(e).lower():
                raise RateLimitError() from e
            elif status_code == 429:
                raise RateLimitError() from e
            elif status_code == 404:
                raise ConnectorError(f"Not found: {url}", error_code="HTTP_404") from e
            elif status_code >= 500:
                raise NetworkError(f"Server error: {status_code}") from e
            else:
                raise ConnectorError(
                    f"HTTP error: {status_code}", error_code=str(status_code)
                ) from e
        except httpx.TimeoutException as e:
            raise NetworkError("Request timeout") from e
        except httpx.ConnectError as e:
            raise NetworkError("Connection error") from e
        except Exception as e:
            raise NetworkError(f"Unexpected error: {e}") from e

        # Update rate limit from response headers
        if use_rate_limit:
            self._update_rate_limit(response)

        # Cache the response if successful
        if use_cache and cache_key and response.status_code == 200:
            self.cache.set(cache_key, response)

        return response

    def _build_cache_key(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None,
        data: dict[str, Any] | None,
        json: dict[str, Any] | None,
    ) -> str | None:
        """Build a cache key for the request."""
        # Only cache GET requests
        if method != "GET":
            return None

        # Sort params for consistent cache keys
        sorted_params = sorted(params.items()) if params else []
        key_parts = [
            method,
            path,
            str(sorted_params),
        ]

        # Include token in cache key (different tokens may see different data)
        if self.token:
            key_parts.append(self.token[:8] + "...")

        return "|".join(key_parts)

    def _update_rate_limit(self, response: Response) -> None:
        """Update rate limit tracker from response headers."""
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")

        if remaining is not None:
            try:
                remaining_int = int(remaining)
                self.rate_limiter.update_remaining(remaining_int)
            except (ValueError, TypeError):
                pass

        if reset is not None:
            try:
                reset_time = datetime.fromtimestamp(int(reset), tz=UTC)
                self.rate_limiter.update_reset(reset_time)
            except (ValueError, TypeError):
                pass

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(
            (
                httpx.ConnectError,
                httpx.TimeoutException,
                httpx.HTTPStatusError,
            )
        ),
    )
    async def _retry_request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None,
        data: dict[str, Any] | None,
        json: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> Response:
        """Make a request with tenacity retry."""
        if self._client is None:
            await self.initialize()
        if self._client is None:  # pragma: no cover - defensive
            raise ConnectorError("HTTP client failed to initialize", is_retriable=False)

        return await self._client.request(
            method,
            url,
            params=params,
            data=data,
            json=json,
            headers=headers,
        )

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        etag: str | None = None,
        use_cache: bool = True,
        use_rate_limit: bool = True,
    ) -> Response:
        """Make a GET request."""
        return await self._make_request(
            "GET",
            path,
            params=params,
            headers=headers,
            etag=etag,
            use_cache=use_cache,
            use_rate_limit=use_rate_limit,
        )

    async def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_cache: bool = False,
        use_rate_limit: bool = True,
    ) -> Response:
        """Make a POST request."""
        return await self._make_request(
            "POST",
            path,
            json=json,
            data=data,
            headers=headers,
            use_cache=use_cache,
            use_rate_limit=use_rate_limit,
        )

    async def put(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_cache: bool = False,
        use_rate_limit: bool = True,
    ) -> Response:
        """Make a PUT request."""
        return await self._make_request(
            "PUT",
            path,
            json=json,
            data=data,
            headers=headers,
            use_cache=use_cache,
            use_rate_limit=use_rate_limit,
        )

    async def delete(
        self,
        path: str,
        headers: dict[str, str] | None = None,
        use_cache: bool = False,
        use_rate_limit: bool = True,
    ) -> Response:
        """Make a DELETE request."""
        return await self._make_request(
            "DELETE",
            path,
            headers=headers,
            use_cache=use_cache,
            use_rate_limit=use_rate_limit,
        )

    async def get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        etag: str | None = None,
        use_cache: bool = True,
        use_rate_limit: bool = True,
    ) -> Any:
        """Make a GET request and return parsed JSON."""
        response = await self.get(
            path,
            params=params,
            headers=headers,
            etag=etag,
            use_cache=use_cache,
            use_rate_limit=use_rate_limit,
        )

        # Handle 304 Not Modified
        if response.status_code == 304:
            return None

        # Ensure successful response
        response.raise_for_status()

        return response.json()

    async def get_paginated(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        page_size: int = 100,
        max_pages: int | None = None,
    ) -> list[Any]:
        """
        Get all paginated results.

        Args:
            path: API path
            params: Query parameters
            page_size: Items per page
            max_pages: Maximum pages to fetch

        Returns:
            List of all items
        """
        items: list[Any] = []
        page = 1

        while True:
            # Add pagination params
            pagination_params = dict(params or {})
            pagination_params["per_page"] = page_size
            pagination_params["page"] = page

            response = await self.get(path, params=pagination_params)

            # Handle 304 Not Modified
            if response.status_code == 304:
                break

            # Ensure successful response
            response.raise_for_status()

            data = response.json()

            # Check if we got items
            if not isinstance(data, list):
                data = data.get("items", data.get("repositories", []))

            if not data:
                break

            items.extend(data)

            # Check if we have more pages
            link_header = response.headers.get("Link", "")
            has_next = 'rel="next"' in link_header

            # Check max pages
            if max_pages is not None and page >= max_pages:
                break

            # Check if we should continue
            if not has_next:
                break

            page += 1

            # Be nice to the API
            await asyncio.sleep(0.1)

        return items

    async def search_repositories(
        self,
        query: str,
        sort: str = "updated",
        order: str = "desc",
        per_page: int = 100,
        max_results: int | None = None,
    ) -> dict[str, Any]:
        """
        Search GitHub repositories.

        Args:
            query: Search query
            sort: Sort field (stars, forks, updated)
            order: Sort order (asc, desc)
            per_page: Results per page
            max_results: Maximum results to return

        Returns:
            Search results
        """
        params = {
            "q": query,
            "sort": sort,
            "order": order,
            "per_page": per_page,
        }

        response = await self.get("/search/repositories", params=params)
        response.raise_for_status()

        return response.json()

    async def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        """Get repository details."""
        path = f"/repos/{owner}/{repo}"
        response = await self.get(path)
        response.raise_for_status()
        return response.json()

    async def get_releases(self, owner: str, repo: str) -> list[dict[str, Any]]:
        """Get all releases for a repository."""
        path = f"/repos/{owner}/{repo}/releases"
        return await self.get_paginated(path)

    async def get_latest_release(self, owner: str, repo: str) -> dict[str, Any] | None:
        """Get the latest release for a repository."""
        path = f"/repos/{owner}/{repo}/releases/latest"
        try:
            response = await self.get(path)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    async def get_contents(
        self,
        owner: str,
        repo: str,
        path: str = "",
        ref: str = "main",
    ) -> list[dict[str, Any]]:
        """Get repository contents."""
        api_path = f"/repos/{owner}/{repo}/contents/{path}"
        params = {"ref": ref}
        return await self.get_paginated(api_path, params=params)

    async def get_readme(self, owner: str, repo: str, ref: str = "main") -> str | None:
        """Get repository README."""
        path = f"/repos/{owner}/{repo}/readme"
        params = {"ref": ref}
        try:
            response = await self.get(path, params=params)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            return data.get("content", "")
        except Exception:
            return None

    async def get_license(self, owner: str, repo: str) -> dict[str, Any] | None:
        """Get repository license."""
        path = f"/repos/{owner}/{repo}/license"
        try:
            response = await self.get(path)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    async def get_topics(self, owner: str, repo: str) -> list[str]:
        """Get repository topics."""
        path = f"/repos/{owner}/{repo}/topics"
        try:
            response = await self.get(path)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            data = response.json()
            return data.get("names", [])
        except Exception:
            return []

    async def get_contributors(self, owner: str, repo: str) -> list[dict[str, Any]]:
        """Get repository contributors."""
        path = f"/repos/{owner}/{repo}/contributors"
        return await self.get_paginated(path, page_size=100, max_pages=10)

    async def get_languages(self, owner: str, repo: str) -> dict[str, int]:
        """Get repository language statistics."""
        path = f"/repos/{owner}/{repo}/languages"
        response = await self.get(path)
        response.raise_for_status()
        return response.json()
