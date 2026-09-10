"""Connector for Gitea-compatible forges (shared by Codeberg and Forgejo)."""

from datetime import datetime
from typing import Any

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings
from omnisource.connectors.base import (
    ConnectorError,
    ConnectorHealth,
    PageInfo,
    SourceConnector,
)
from omnisource.connectors.gitea.client import GiteaClient, parse_iso_datetime
from omnisource.core.models.release import (
    detect_architecture,
    detect_package_type,
    detect_platform,
)
from omnisource.core.schemas.asset import AssetSchema, AssetSourceSchema, AssetStatusSchema
from omnisource.core.schemas.release import ReleaseSchema, ReleaseStatusSchema
from omnisource.core.schemas.repository import (
    RepositorySchema,
    RepositoryStatus,
    RepositoryVisibility,
)

logger = get_logger(__name__)


class GiteaConnectorBase(SourceConnector):
    """Base for forges exposing the Gitea API. Subclasses set URLs."""

    source_name = "gitea"
    source_type = "gitea"
    base_url = "https://codeberg.org"
    api_url = "https://codeberg.org/api/v1"

    _settings_token_attr = "CODEBERG_TOKEN"  # noqa: S105 - settings key name, not a secret

    def __init__(
        self,
        token: str | None = None,
        base_url: str | None = None,
        api_url: str | None = None,
    ) -> None:
        super().__init__()
        settings = get_settings()
        default_token = getattr(settings.sources, self._settings_token_attr, None)
        self.token = token if token is not None else default_token
        if base_url:
            self.base_url = base_url
        if api_url:
            self.api_url = api_url
        self._client: GiteaClient | None = None

    async def initialize(self) -> None:
        self._client = GiteaClient(api_url=self.api_url, token=self.token)
        await self._client.initialize()
        self._initialized = True
        logger.info("%s connector initialized (%s)", self.source_name, self.api_url)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
        self._initialized = False

    def _require_client(self) -> GiteaClient:
        if self._client is None:
            raise ConnectorError(
                f"{self.source_name} connector not initialized", is_retriable=False
            )
        return self._client

    # --- Interface ----------------------------------------------------------

    async def discover(
        self,
        query: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
        **kwargs: Any,
    ) -> tuple[list[RepositorySchema], PageInfo]:
        client = self._require_client()
        page = 1
        if cursor:
            try:
                page = max(1, int(cursor))
            except ValueError:
                page = 1

        items = await client.search_repositories(query=query, page=page, limit=min(limit, 50))
        repositories = [self._to_repository_schema(item) for item in items]

        has_next = len(items) >= min(limit, 50)
        page_info = PageInfo(
            page=page,
            per_page=min(limit, 50),
            total=len(repositories),
            total_pages=page + 1 if has_next else page,
            has_next=has_next,
            has_previous=page > 1,
            next_cursor=str(page + 1) if has_next else None,
            prev_cursor=str(page - 1) if page > 1 else None,
        )
        return repositories, page_info

    async def get_repository(self, repository_id: str, **kwargs: Any) -> RepositorySchema:
        client = self._require_client()
        owner, repo = self._parse_repository_id(repository_id)
        data = await client.get_repository(owner, repo)
        return self._to_repository_schema(data)

    async def get_releases(
        self, repository: RepositorySchema, **kwargs: Any
    ) -> list[ReleaseSchema]:
        client = self._require_client()
        owner, repo = self._parse_repository_id(repository.full_name)
        data = await client.get_releases(owner, repo)
        return [self._to_release_schema(item, repository) for item in data]

    async def get_assets(self, release: ReleaseSchema, **kwargs: Any) -> list[AssetSchema]:
        assets: list[AssetSchema] = []
        for item in release.assets or []:
            if not isinstance(item, dict):
                continue
            filename = item.get("name", "")
            package_type = detect_package_type(filename)
            assets.append(
                AssetSchema(
                    asset_id=f"{self.source_name}-{item.get('id', '')}",
                    filename=filename,
                    display_name=item.get("name"),
                    download_url=item.get("browser_download_url") or "",
                    size_bytes=item.get("size"),
                    mime_type=item.get("content_type"),
                    file_type=package_type.value,
                    detected_platform=detect_platform(filename),
                    detected_architecture=detect_architecture(filename),
                    package_type=package_type.value,
                    version=release.version,
                    source=AssetSourceSchema.OFFICIAL,
                    status=AssetStatusSchema.PENDING,
                    release_id=release.id,
                )
            )
        return assets

    async def get_metadata(self, repository: RepositorySchema, **kwargs: Any) -> dict[str, Any]:
        client = self._require_client()
        owner, repo = self._parse_repository_id(repository.full_name)
        metadata: dict[str, Any] = {}
        try:
            metadata["languages"] = await client.get_languages(owner, repo)
        except ConnectorError:
            pass
        try:
            metadata["topics"] = await client.get_topics(owner, repo)
        except ConnectorError:
            pass
        return metadata

    async def health_check(self) -> ConnectorHealth:
        started = datetime.now()
        try:
            await self._require_client().version()
            latency_ms = (datetime.now() - started).total_seconds() * 1000
            self.update_health(
                healthy=True,
                latency_ms=latency_ms,
                last_check=datetime.now(),
                last_success=datetime.now(),
            )
        except Exception as exc:
            self.update_health(healthy=False, last_check=datetime.now(), last_error=str(exc))
        return self._health

    # --- Helpers -------------------------------------------------------------

    @staticmethod
    def _parse_repository_id(repository_id: str) -> tuple[str, str]:
        if "/" not in repository_id:
            raise ConnectorError(
                f"Invalid repository ID format: {repository_id}", is_retriable=False
            )
        owner, repo = repository_id.split("/", 1)
        return owner, repo

    def _to_repository_schema(self, item: dict[str, Any]) -> RepositorySchema:
        owner = item.get("owner") or {}
        full_name = item.get("full_name") or (f"{owner.get('login', '')}/{item.get('name', '')}")
        return RepositorySchema(
            external_id=str(item.get("id", "")),
            full_name=full_name,
            name=item.get("name", ""),
            description=item.get("description"),
            homepage=item.get("website") or None,
            html_url=item.get("html_url") or f"{self.base_url}/{full_name}",
            api_url=item.get("_links", {}).get("self")
            if isinstance(item.get("_links"), dict)
            else None,
            status=RepositoryStatus.ARCHIVED if item.get("archived") else RepositoryStatus.ACTIVE,
            visibility=RepositoryVisibility.PUBLIC,
            is_fork=bool(item.get("fork")),
            is_archived=bool(item.get("archived")),
            stars=int(item.get("stars_count") or 0),
            forks=int(item.get("forks_count") or 0),
            open_issues=int(item.get("open_issues_count") or 0),
            size_kb=int(item.get("size") or 0),
            language=item.get("language") or None,
            default_branch=item.get("default_branch"),
            created_at_external=parse_iso_datetime(item.get("created_at")),
            updated_at_external=parse_iso_datetime(item.get("updated_at")),
            pushed_at=parse_iso_datetime(item.get("updated_at")),
            license_spdx=None,  # Gitea search results do not carry license info
            topics=item.get("topics", []) or [],
            source_type=self.source_type,
        )

    def _to_release_schema(
        self, item: dict[str, Any], repository: RepositorySchema
    ) -> ReleaseSchema:
        is_draft = bool(item.get("draft"))
        is_prerelease = bool(item.get("prerelease"))
        if is_draft:
            status = ReleaseStatusSchema.DRAFT
        elif is_prerelease:
            status = ReleaseStatusSchema.PRERELEASE
        else:
            status = ReleaseStatusSchema.RELEASED
        return ReleaseSchema(
            external_id=str(item.get("id", "")),
            version=item.get("tag_name") or "",
            tag=item.get("tag_name"),
            name=item.get("name"),
            body=item.get("body"),
            status=status,
            is_prerelease=is_prerelease,
            is_draft=is_draft,
            published_at=parse_iso_datetime(item.get("published_at")),
            created_at_external=parse_iso_datetime(item.get("created_at")),
            tarball_url=item.get("tarball_url"),
            zipball_url=item.get("zipball_url"),
            download_count=0,
            repository_id=repository.id,
            assets=item.get("assets", []) or [],
        )
