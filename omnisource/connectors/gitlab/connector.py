"""GitLab connector implementation for OmniSource."""

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings
from omnisource.connectors.base import (
    ConnectorError,
    ConnectorHealth,
    PageInfo,
    SourceConnector,
)
from omnisource.connectors.rate_limiter import RateLimiter
from omnisource.core.models.release import detect_architecture, detect_package_type, detect_platform
from omnisource.core.schemas.asset import AssetSchema, AssetSourceSchema, AssetStatusSchema
from omnisource.core.schemas.release import ReleaseSchema, ReleaseStatusSchema
from omnisource.core.schemas.repository import (
    RepositorySchema,
    RepositoryStatus,
    RepositoryVisibility,
)

logger = get_logger(__name__)


class GitLabConnector(SourceConnector):
    """GitLab API v4 connector."""

    source_name = "gitlab"
    source_type = "gitlab"
    base_url = "https://gitlab.com"
    api_url = "https://gitlab.com/api/v4"

    def __init__(
        self,
        token: str | None = None,
        base_url: str | None = None,
        api_url: str | None = None,
    ):
        super().__init__()
        settings = get_settings()
        self.token = token or settings.sources.GITLAB_TOKEN
        self.base_url = base_url or self.base_url
        self.api_url = api_url or self.api_url
        self.rate_limiter = RateLimiter(max_requests=2000, period=timedelta(minutes=1))
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        headers = {"Accept": "application/json", "User-Agent": "OmniSource/0.1.0"}
        if self.token:
            headers["PRIVATE-TOKEN"] = self.token
        self._client = httpx.AsyncClient(base_url=self.api_url, headers=headers, timeout=30.0)
        self._initialized = True
        logger.info("GitLab connector initialized")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self._client:
            raise ConnectorError("Connector not initialized", is_retriable=False)
        await self.rate_limiter.wait_for_token()
        response = await self._client.get(path, params=params)
        if response.status_code == 404:
            raise ConnectorError(f"Not found: {path}", error_code="HTTP_404")
        if response.status_code == 401:
            raise ConnectorError(
                "GitLab authentication failed", error_code="AUTH_ERROR", is_retriable=False
            )
        if response.status_code in (429, 502, 503):
            raise ConnectorError(f"GitLab error {response.status_code}", error_code="RATE_LIMIT")
        response.raise_for_status()
        return response.json()

    async def discover(
        self,
        query: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
        **kwargs: Any,
    ) -> tuple[list[RepositorySchema], PageInfo]:
        page = 1
        if cursor:
            try:
                page = int(cursor)
            except ValueError:
                page = 1

        params: dict[str, Any] = {
            "simple": True,
            "per_page": min(limit, 100),
            "page": page,
            "order_by": "last_activity_at",
        }
        if query:
            params["search"] = query

        data = await self._get("/projects", params=params)
        repositories = [self._to_repository_schema(item) for item in data]

        has_next = len(data) == params["per_page"]
        page_info = PageInfo(
            page=page,
            per_page=params["per_page"],
            total=len(repositories),
            total_pages=page + 1 if has_next else page,
            has_next=has_next,
            has_previous=page > 1,
            next_cursor=str(page + 1) if has_next else None,
            prev_cursor=str(page - 1) if page > 1 else None,
        )
        return repositories, page_info

    async def get_repository(self, repository_id: str, **kwargs: Any) -> RepositorySchema:
        path = f"/projects/{quote(repository_id, safe='')}"
        data = await self._get(path)
        return self._to_repository_schema(data)

    async def get_releases(
        self, repository: RepositorySchema, **kwargs: Any
    ) -> list[ReleaseSchema]:
        project_id = repository.external_id or repository.full_name
        data = await self._get(f"/projects/{quote(project_id, safe='')}/releases")
        releases = []
        for item in data:
            releases.append(
                ReleaseSchema(
                    external_id=str(item.get("name", "")),
                    version=item.get("tag_name", ""),
                    tag=item.get("tag_name"),
                    name=item.get("name"),
                    body=item.get("description"),
                    status=ReleaseStatusSchema.RELEASED,
                    is_prerelease=bool(item.get("upcoming_release", False)),
                    published_at=self._parse_datetime(item.get("released_at")),
                    commit_sha=item.get("commit", {}).get("id")
                    if isinstance(item.get("commit"), dict)
                    else None,
                    repository_id=repository.id,
                    assets=item.get("assets", {}),
                )
            )
        releases.sort(key=lambda r: r.published_at or datetime.min, reverse=True)
        return releases

    async def get_assets(self, release: ReleaseSchema, **kwargs: Any) -> list[AssetSchema]:
        assets: list[AssetSchema] = []
        raw_assets = release.assets or []
        if isinstance(raw_assets, dict):
            raw_assets = raw_assets.get("links", [])

        for item in raw_assets:
            filename = item.get("name", "")
            package_type = detect_package_type(filename)
            assets.append(
                AssetSchema(
                    asset_id=f"gl-{item.get('id', '')}",
                    filename=filename,
                    display_name=item.get("name"),
                    download_url=item.get("direct_asset_url") or item.get("url", ""),
                    size_bytes=None,
                    mime_type=item.get("link_type"),
                    file_type=package_type.value,
                    detected_platform=detect_platform(filename),
                    detected_architecture=detect_architecture(filename),
                    package_type=package_type.value,
                    version=release.version,
                    source=AssetSourceSchema.OTHER,
                    status=AssetStatusSchema.PENDING,
                    release_id=release.id,
                )
            )
        return assets

    async def get_metadata(self, repository: RepositorySchema, **kwargs: Any) -> dict[str, Any]:
        project_id = repository.external_id or repository.full_name
        safe = quote(project_id, safe="")
        metadata: dict[str, Any] = {}
        try:
            metadata["languages"] = await self._get(f"/projects/{safe}/languages")
        except ConnectorError:
            pass
        try:
            metadata["contributors"] = await self._get(f"/projects/{safe}/repository/contributors")
        except ConnectorError:
            pass
        try:
            metadata["topics"] = await self._get(f"/projects/{safe}/topics")
        except ConnectorError:
            pass
        return metadata

    async def health_check(self) -> ConnectorHealth:
        try:
            start = datetime.now()
            await self._get("/version")
            latency = (datetime.now() - start).total_seconds() * 1000
            self.update_health(
                healthy=True,
                latency_ms=latency,
                last_check=datetime.now(),
                last_success=datetime.now(),
            )
        except Exception as exc:
            self.update_health(healthy=False, last_check=datetime.now(), last_error=str(exc))
        return self._health

    def _to_repository_schema(self, item: dict[str, Any]) -> RepositorySchema:
        namespace = item.get("namespace", {})
        full_name = item.get("path_with_namespace") or item.get("path") or ""
        namespace.get("path", "")
        return RepositorySchema(
            external_id=str(item.get("id", "")),
            full_name=full_name,
            name=item.get("name") or item.get("path", ""),
            description=item.get("description"),
            homepage=None,
            html_url=item.get("web_url", ""),
            api_url=item.get("_links", {}).get("self")
            if isinstance(item.get("_links"), dict)
            else None,
            status=RepositoryStatus.ARCHIVED if item.get("archived") else RepositoryStatus.ACTIVE,
            visibility=RepositoryVisibility(item.get("visibility", "public")),
            is_fork=bool(item.get("fork")),
            is_archived=bool(item.get("archived")),
            stars=int(item.get("star_count") or 0),
            forks=int(item.get("forks_count") or 0),
            open_issues=int(item.get("open_issues_count") or 0),
            size_kb=0,
            language=item.get("language") or None,
            default_branch=item.get("default_branch"),
            created_at_external=self._parse_datetime(item.get("created_at")),
            updated_at_external=self._parse_datetime(item.get("last_activity_at")),
            pushed_at=self._parse_datetime(item.get("last_activity_at")),
            license_spdx=item.get("license", {}).get("key")
            if isinstance(item.get("license"), dict)
            else None,
            topics=item.get("topics", []),
            source_type="gitlab",
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
