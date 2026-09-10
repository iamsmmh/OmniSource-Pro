"""F-Droid connector for OmniSource.

Uses the official F-Droid package API (``/api/v1``):

- ``GET /packages``                        → all package IDs
- ``GET /packages/{packageId}``            → package + version list

Mapping onto the connector interface:

- **discover** pages through the package-ID list (offset cursor) and materializes
  each package into a repository schema.
- **get_releases** maps each F-Droid *version* of a package to a release whose
  asset is the APK at ``https://f-droid.org/repo/{package}_{versionCode}.apk``.
"""

from datetime import datetime, timedelta
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
from omnisource.connectors.rate_limiter import RateLimiter
from omnisource.core.models.release import detect_package_type
from omnisource.core.schemas.asset import AssetSchema, AssetSourceSchema, AssetStatusSchema
from omnisource.core.schemas.release import ReleaseSchema, ReleaseStatusSchema
from omnisource.core.schemas.repository import (
    RepositorySchema,
    RepositoryStatus,
    RepositoryVisibility,
)

logger = get_logger(__name__)

_USER_AGENT = "OmniSource/0.1.0"


class FDroidConnector(SourceConnector):
    """F-Droid API v1 connector."""

    source_name = "fdroid"
    source_type = "fdroid"
    base_url = "https://f-droid.org"
    api_url = "https://f-droid.org/api/v1"

    def __init__(
        self,
        api_url: str | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__()
        settings = get_settings()
        self.api_url = api_url or settings.sources.FDROID_API_URL
        self.rate_limiter = rate_limiter or RateLimiter(
            max_requests=600, period=timedelta(minutes=1)
        )
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
        self._client = httpx.AsyncClient(
            base_url=self.api_url.rstrip("/"), headers=headers, timeout=30.0
        )
        self._initialized = True
        logger.info("F-Droid connector initialized (%s)", self.api_url)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._initialized = False

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ConnectorError("F-Droid connector not initialized", is_retriable=False)
        return self._client

    async def _get(self, path: str) -> Any:
        client = self._require_client()
        await self.rate_limiter.wait_for_token()
        try:
            response = await client.get(path)
        except httpx.TimeoutException as e:
            raise ConnectorError(f"Timeout requesting {path}") from e
        except httpx.ConnectError as e:
            raise ConnectorError(f"Connection error requesting {path}") from e
        if response.status_code == 404:
            raise ConnectorError(f"Not found: {path}", error_code="HTTP_404")
        if response.status_code >= 500:
            raise ConnectorError(
                f"F-Droid API error {response.status_code}", error_code="RATE_LIMIT"
            )
        response.raise_for_status()
        return response.json()

    # --- Interface -------------------------------------------------------------

    async def discover(
        self,
        query: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
        **kwargs: Any,
    ) -> tuple[list[RepositorySchema], PageInfo]:
        """Page through the full F-Droid package list using an offset cursor."""
        raw_packages = await self._get("/packages")
        if not isinstance(raw_packages, list):
            raise ConnectorError("Unexpected F-Droid /packages payload", is_retriable=False)
        # The API returns either plain IDs or objects with a packageName key.
        package_ids: list[str] = []
        for entry in raw_packages:
            if isinstance(entry, str):
                package_ids.append(entry)
            elif isinstance(entry, dict) and entry.get("packageName"):
                package_ids.append(str(entry["packageName"]))

        offset = 0
        if cursor:
            try:
                offset = max(0, int(cursor))
            except ValueError:
                offset = 0

        window = package_ids[offset : offset + limit]
        repositories: list[RepositorySchema] = []
        for package_id in window:
            repositories.append(self._package_to_repository(package_id))

        next_offset = offset + len(window)
        has_next = next_offset < len(package_ids)
        page_info = PageInfo(
            page=(offset // limit) + 1,
            per_page=limit,
            total=len(package_ids),
            has_next=has_next,
            has_previous=offset > 0,
            next_cursor=str(next_offset) if has_next else None,
            prev_cursor=str(max(0, offset - limit)) if offset > 0 else None,
        )

        if query:
            lowered = query.lower()
            repositories = [
                r
                for r in repositories
                if lowered in r.name.lower() or lowered in (r.description or "").lower()
            ]
        return repositories, page_info

    async def get_repository(self, repository_id: str, **kwargs: Any) -> RepositorySchema:
        data = await self._get(f"/packages/{repository_id}")
        return self._detail_to_repository(data)

    async def get_releases(
        self, repository: RepositorySchema, **kwargs: Any
    ) -> list[ReleaseSchema]:
        data = await self._get(f"/packages/{repository.external_id}")
        releases: list[ReleaseSchema] = []
        for pkg in reversed(data.get("packages", []) or []):
            version_name = str(pkg.get("versionName", ""))
            version_code = pkg.get("versionCode")
            releases.append(
                ReleaseSchema(
                    external_id=f"{repository.external_id}-{version_code}",
                    version=version_name,
                    tag=None,
                    name=f"{repository.external_id} {version_name}",
                    body=None,
                    status=ReleaseStatusSchema.RELEASED,
                    published_at=None,
                    repository_id=repository.id,
                    assets=[
                        {
                            "id": f"{repository.external_id}-{version_code}",
                            "name": f"{repository.external_id}_{version_code}.apk",
                            "versionCode": version_code,
                            "minSdkVersion": pkg.get("minSdkVersion"),
                            "targetSdkVersion": pkg.get("targetSdkVersion"),
                        }
                    ],
                )
            )
        return releases

    async def get_assets(self, release: ReleaseSchema, **kwargs: Any) -> list[AssetSchema]:
        assets: list[AssetSchema] = []
        for item in release.assets or []:
            if not isinstance(item, dict):
                continue
            filename = str(item.get("name", ""))
            package_type = detect_package_type(filename)
            assets.append(
                AssetSchema(
                    asset_id=f"fdroid-{item.get('id', '')}",
                    filename=filename,
                    display_name=filename,
                    download_url=f"{self.base_url}/repo/{filename}",
                    size_bytes=None,
                    mime_type="application/vnd.android.package-archive",
                    file_type=package_type.value,
                    detected_platform="android",
                    detected_architecture="any",
                    package_type=package_type.value,
                    version=release.version,
                    source=AssetSourceSchema.OFFICIAL,
                    status=AssetStatusSchema.PENDING,
                    release_id=release.id,
                )
            )
        return assets

    async def get_metadata(self, repository: RepositorySchema, **kwargs: Any) -> dict[str, Any]:
        # The v1 API is intentionally thin; nothing extra to fetch today.
        return {"source": "fdroid", "package": repository.external_id}

    async def health_check(self) -> ConnectorHealth:
        started = datetime.now()
        try:
            await self._require_client().get("/packages")
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

    # --- Helpers -----------------------------------------------------------------

    def _package_to_repository(self, package_id: str) -> RepositorySchema:
        return RepositorySchema(
            external_id=package_id,
            full_name=package_id,
            name=package_id.rsplit(".", 1)[-1],
            description=None,
            homepage=f"{self.base_url}/packages/{package_id}",
            html_url=f"{self.base_url}/packages/{package_id}",
            api_url=f"{self.api_url}/packages/{package_id}",
            status=RepositoryStatus.ACTIVE,
            visibility=RepositoryVisibility.PUBLIC,
            source_type=self.source_type,
        )

    def _detail_to_repository(self, data: dict[str, Any]) -> RepositorySchema:
        package_id = data.get("packageName", "")
        packages = data.get("packages", []) or []
        last = packages[-1] if packages else {}
        updated = last.get("lastUpdated")
        return RepositorySchema(
            external_id=package_id,
            full_name=package_id,
            name=package_id.rsplit(".", 1)[-1],
            description=data.get("description"),
            homepage=f"{self.base_url}/packages/{package_id}",
            html_url=f"{self.base_url}/packages/{package_id}",
            api_url=f"{self.api_url}/packages/{package_id}",
            status=RepositoryStatus.ACTIVE,
            visibility=RepositoryVisibility.PUBLIC,
            updated_at_external=(
                datetime.fromtimestamp(updated / 1000)
                if isinstance(updated, (int, float)) and updated > 10**12
                else datetime.fromtimestamp(updated)
                if isinstance(updated, (int, float))
                else None
            ),
            source_type=self.source_type,
        )
