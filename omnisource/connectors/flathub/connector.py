"""Flathub connector for OmniSource.

Uses the Flathub REST API:

- ``GET /api/v1/apps``               → collection listing (id, name, summary)
- ``GET /api/v1/apps/{id}``          → app detail (description, releases, ...)
- ``GET /api/v2/appstream/{id}``     → appstream metadata (releases, icons)

Mapping onto the connector interface:

- Flathub *application IDs* (``com.example.App``) act as repositories.
- Each appstream **release** entry maps to a release.
- Release assets are the flatpakref / flatpak bundle links plus any installer
  files exposed by the API.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings
from omnisource.connectors.base import (
    ConnectorError,
    ConnectorHealth,
    PageInfo,
    SourceConnector,
)
from omnisource.connectors.http import get_with_retry
from omnisource.connectors.rate_limiter import RateLimiter
from omnisource.core.schemas.asset import AssetSchema, AssetSourceSchema, AssetStatusSchema
from omnisource.core.schemas.release import ReleaseSchema, ReleaseStatusSchema
from omnisource.core.schemas.repository import (
    RepositorySchema,
    RepositoryStatus,
    RepositoryVisibility,
)

logger = get_logger(__name__)

_USER_AGENT = "OmniSource/0.1.0"


class FlathubConnector(SourceConnector):
    """Flathub REST API connector."""

    source_name = "flathub"
    source_type = "flathub"
    base_url = "https://flathub.org"
    api_url = "https://flathub.org/api/v1"
    api_v2_url = "https://flathub.org/api/v2"

    def __init__(
        self,
        api_url: str | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__()
        settings = get_settings()
        self.api_url = (api_url or settings.sources.FLATHUB_API_URL).rstrip("/")
        if not self.api_url.endswith("/api/v1"):
            self.api_url = f"{self.api_url}/api/v1"
        self.rate_limiter = rate_limiter or RateLimiter(
            max_requests=600, period=timedelta(minutes=1)
        )
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
        self._client = httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=30.0)
        self._initialized = True
        logger.info("Flathub connector initialized (%s)", self.api_url)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._initialized = False

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ConnectorError("Flathub connector not initialized", is_retriable=False)
        return self._client

    async def _get(self, path: str) -> Any:
        client = self._require_client()
        # Paths are relative to the v1 API unless they already carry /api/.
        request_path = path if path.startswith("/api/") else f"{self.api_url}{path}"
        response = await get_with_retry(client, request_path, limiter=self.rate_limiter)
        if response.status_code == 404:
            raise ConnectorError(f"Not found: {path}", error_code="HTTP_404")
        if response.status_code >= 500 or response.status_code == 429:
            raise ConnectorError(
                f"Flathub API error {response.status_code}", error_code="RATE_LIMIT"
            )
        response.raise_for_status()
        return response.json()

    # --- Interface ---------------------------------------------------------------

    async def discover(
        self,
        query: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
        **kwargs: Any,
    ) -> tuple[list[RepositorySchema], PageInfo]:
        offset = 0
        if cursor:
            try:
                offset = max(0, int(cursor))
            except ValueError:
                offset = 0

        apps = await self._get("/apps")
        if not isinstance(apps, list):
            raise ConnectorError("Unexpected Flathub /apps payload", is_retriable=False)

        if query:
            lowered = query.lower()
            apps = [
                a
                for a in apps
                if lowered in str(a.get("name", "")).lower()
                or lowered in str(a.get("summary", "")).lower()
                or lowered in str(a.get("flatpakAppId", "")).lower()
            ]

        window = apps[offset : offset + limit]
        repositories = [self._listing_to_repository(a) for a in window if isinstance(a, dict)]

        next_offset = offset + len(window)
        has_next = next_offset < len(apps)
        page_info = PageInfo(
            page=(offset // limit) + 1,
            per_page=limit,
            total=len(apps),
            has_next=has_next,
            has_previous=offset > 0,
            next_cursor=str(next_offset) if has_next else None,
            prev_cursor=str(max(0, offset - limit)) if offset > 0 else None,
        )
        return repositories, page_info

    async def get_repository(self, repository_id: str, **kwargs: Any) -> RepositorySchema:
        data = await self._get(f"/apps/{repository_id}")
        return self._detail_to_repository(data)

    async def get_releases(
        self, repository: RepositorySchema, **kwargs: Any
    ) -> list[ReleaseSchema]:
        """Releases come from the v2 appstream endpoint when available."""
        app_id = repository.external_id
        releases: list[ReleaseSchema] = []
        try:
            stream = await self._get(f"/api/v2/appstream/{app_id}")
        except ConnectorError:
            stream = {}

        for item in (stream.get("releases") or []) if isinstance(stream, dict) else []:
            if not isinstance(item, dict):
                continue
            version = str(item.get("version", ""))
            if not version:
                continue
            releases.append(
                ReleaseSchema(
                    external_id=f"flathub-{app_id}-{version}",
                    version=version,
                    tag=None,
                    name=f"{app_id} {version}",
                    body=item.get("description"),
                    status=ReleaseStatusSchema.RELEASED,
                    published_at=self._parse_timestamp(item.get("timestamp") or item.get("date")),
                    repository_id=repository.id,
                    assets=[],
                )
            )
        return releases

    async def get_assets(self, release: ReleaseSchema, **kwargs: Any) -> list[AssetSchema]:
        """Flathub apps ship as flatpakref/flatpak bundles, not per-release files."""
        app_id = (release.name or "").split(" ")[0] if release.name else ""
        if not app_id:
            app_id = str(release.external_id).replace("flathub-", "").rsplit("-", 1)[0]
        ref_url = f"{self.base_url}/repo/appstream/x86_64/{app_id}.flatpakref"
        assets = [
            AssetSchema(
                asset_id=f"flathub-{app_id}-ref",
                filename=f"{app_id}.flatpakref",
                display_name=f"{app_id} flatpakref",
                download_url=ref_url,
                size_bytes=None,
                mime_type="application/vnd.flatpak.ref",
                file_type="flatpakref",
                detected_platform="linux",
                detected_architecture="x86_64",
                package_type="flatpakref",
                version=release.version,
                source=AssetSourceSchema.OFFICIAL,
                status=AssetStatusSchema.PENDING,
                release_id=release.id,
            )
        ]
        return assets

    async def get_metadata(self, repository: RepositorySchema, **kwargs: Any) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        try:
            stream = await self._get(f"/api/v2/appstream/{repository.external_id}")
            if isinstance(stream, dict):
                metadata["screenshots"] = stream.get("screenshots")
                metadata["icon"] = stream.get("icon")
                metadata["categories"] = stream.get("categories")
        except ConnectorError:
            pass
        return metadata

    async def health_check(self) -> ConnectorHealth:
        started = datetime.now()
        try:
            await self._get("/apps")
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

    # --- Helpers --------------------------------------------------------------------

    def _listing_to_repository(self, item: dict[str, Any]) -> RepositorySchema:
        app_id = str(item.get("flatpakAppId") or item.get("id") or "")
        return RepositorySchema(
            external_id=app_id,
            full_name=app_id,
            name=str(item.get("name") or app_id.rsplit(".", 1)[-1]),
            description=item.get("summary"),
            homepage=f"{self.base_url}/apps/{app_id}",
            html_url=f"{self.base_url}/apps/{app_id}",
            api_url=f"{self.api_url}/apps/{app_id}",
            status=RepositoryStatus.ACTIVE,
            visibility=RepositoryVisibility.PUBLIC,
            stars=int(item.get("favorites") or 0),
            source_type=self.source_type,
        )

    def _detail_to_repository(self, item: dict[str, Any]) -> RepositorySchema:
        app_id = str(item.get("flatpakAppId") or item.get("id") or item.get("appId") or "")
        in_store = bool(item.get("inStore", True))
        return RepositorySchema(
            external_id=app_id,
            full_name=app_id,
            name=str(item.get("name") or app_id.rsplit(".", 1)[-1]),
            description=item.get("summary") or item.get("description"),
            homepage=item.get("homepage") or f"{self.base_url}/apps/{app_id}",
            html_url=f"{self.base_url}/apps/{app_id}",
            api_url=f"{self.api_url}/apps/{app_id}",
            status=RepositoryStatus.ACTIVE if in_store else RepositoryStatus.ARCHIVED,
            is_archived=not in_store,
            visibility=RepositoryVisibility.PUBLIC,
            license_spdx=self._first_license(item),
            updated_at_external=self._parse_timestamp(item.get("inStoreSinceDate")),
            source_type=self.source_type,
        )

    @staticmethod
    def _first_license(item: dict[str, Any]) -> str | None:
        license_value = (
            item.get("projectLicense")
            or item.get("license")
            or item.get("currentRelease", {}).get("license")
            if isinstance(item.get("currentRelease"), dict)
            else item.get("projectLicense") or item.get("license")
        )
        return str(license_value) if license_value else None

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=UTC)
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.strptime(str(value), "%Y-%m-%d").replace(tzinfo=UTC)
            except ValueError:
                return None
