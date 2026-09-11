"""Homebrew connector for OmniSource.

Uses the official Homebrew JSON API at ``formulae.brew.sh``:

- ``GET /api/formula.json``        → all formulae (large; paged client-side)
- ``GET /api/formula/{name}.json`` → formula detail (versions, bottle urls)
- ``GET /api/cask.json``           → all casks
- ``GET /api/cask/{token}.json``   → cask detail (url, sha256, version)

Mapping:

- A formula/cask token acts as the repository identifier.
- The stable version maps to a release.
- For formulae, the bottle files (ghcr.io) plus the source tarball map to
  assets; casks expose ``url``/``sha256`` directly.
"""

from datetime import datetime, timedelta
from typing import Any

import httpx

from omnisource.config.logging import get_logger
from omnisource.connectors.base import (
    ConnectorError,
    ConnectorHealth,
    PageInfo,
    SourceConnector,
)
from omnisource.connectors.http import get_with_retry
from omnisource.connectors.rate_limiter import RateLimiter
from omnisource.core.models.release import (
    detect_architecture,
    detect_package_type,
    detect_platform,
)
from omnisource.core.schemas.asset import (
    AssetSchema,
    AssetSourceSchema,
    AssetStatusSchema,
)
from omnisource.core.schemas.release import ReleaseSchema, ReleaseStatusSchema
from omnisource.core.schemas.repository import (
    RepositorySchema,
    RepositoryStatus,
    RepositoryVisibility,
)

logger = get_logger(__name__)

_USER_AGENT = "OmniSource/0.1.0"
_API_BASE = "https://formulae.brew.sh/api"


class HomebrewConnector(SourceConnector):
    """Homebrew formulae/casks API connector."""

    source_name = "homebrew"
    source_type = "homebrew"
    base_url = "https://formulae.brew.sh"
    api_url = _API_BASE

    def __init__(
        self,
        api_url: str | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__()
        self.api_url = (api_url or self.api_url).rstrip("/")
        self.rate_limiter = rate_limiter or RateLimiter(
            max_requests=400, period=timedelta(minutes=1)
        )
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
        self._client = httpx.AsyncClient(base_url=self.api_url, headers=headers, timeout=60.0)
        self._initialized = True
        logger.info("Homebrew connector initialized (%s)", self.api_url)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._initialized = False

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ConnectorError("Homebrew connector not initialized", is_retriable=False)
        return self._client

    async def _get(self, path: str) -> Any:
        client = self._require_client()
        response = await get_with_retry(client, path, limiter=self.rate_limiter)
        if response.status_code == 404:
            raise ConnectorError(f"Not found: {path}", error_code="HTTP_404")
        if response.status_code == 429 or response.status_code >= 500:
            raise ConnectorError(
                f"Homebrew API error {response.status_code}", error_code="RATE_LIMIT"
            )
        response.raise_for_status()
        return response.json()

    # --- Interface -----------------------------------------------------------------

    async def discover(
        self,
        query: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
        **kwargs: Any,
    ) -> tuple[list[RepositorySchema], PageInfo]:
        """Discover formulae and casks from the full-list endpoints."""
        offset = 0
        if cursor:
            try:
                offset = max(0, int(cursor))
            except ValueError:
                offset = 0

        formulae = await self._get("/formula.json")
        casks = await self._get("/cask.json")
        if not isinstance(formulae, list) or not isinstance(casks, list):
            raise ConnectorError("Unexpected Homebrew listing payload", is_retriable=False)

        repositories = [self._summary_to_repository(f, "formula") for f in formulae]
        repositories += [self._summary_to_repository(c, "cask") for c in casks]

        if query:
            lowered = query.lower()
            repositories = [
                r
                for r in repositories
                if lowered in r.name.lower() or lowered in (r.description or "").lower()
            ]

        window = repositories[offset : offset + limit]
        next_offset = offset + len(window)
        has_next = next_offset < len(repositories)
        page_info = PageInfo(
            page=(offset // limit) + 1,
            per_page=limit,
            total=len(repositories),
            has_next=has_next,
            has_previous=offset > 0,
            next_cursor=str(next_offset) if has_next else None,
            prev_cursor=str(max(0, offset - limit)) if offset > 0 else None,
        )
        return window, page_info

    async def _fetch_detail(self, token: str) -> dict[str, Any]:
        """Fetch formula (then cask) detail for a token; includes ``kind`` key."""
        try:
            data = await self._get(f"/formula/{token}.json")
            data["omni_kind"] = "formula"
            return data
        except ConnectorError as exc:
            if exc.error_code != "HTTP_404":
                raise
        data = await self._get(f"/cask/{token}.json")
        data["omni_kind"] = "cask"
        return data

    async def get_repository(self, repository_id: str, **kwargs: Any) -> RepositorySchema:
        data = await self._fetch_detail(repository_id)
        return self._detail_to_repository(data)

    async def get_releases(
        self, repository: RepositorySchema, **kwargs: Any
    ) -> list[ReleaseSchema]:
        data = await self._fetch_detail(repository.external_id)
        version = str((data.get("versions") or {}).get("stable") or data.get("version") or "")
        if not version:
            return []
        return [
            ReleaseSchema(
                external_id=f"homebrew-{repository.external_id}-{version}",
                version=version,
                tag=version,
                name=f"{repository.name} {version}",
                body=None,
                status=ReleaseStatusSchema.RELEASED,
                repository_id=repository.id,
                assets=self._extract_asset_payloads(data),
            )
        ]

    async def get_assets(self, release: ReleaseSchema, **kwargs: Any) -> list[AssetSchema]:
        assets: list[AssetSchema] = []
        for item in release.assets or []:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            url = str(item["url"])
            filename = url.rsplit("/", 1)[-1] or url
            package_type = detect_package_type(filename)
            assets.append(
                AssetSchema(
                    asset_id=f"homebrew-{item.get('kind', 'asset')}-{filename}",
                    filename=filename,
                    display_name=filename,
                    download_url=url,
                    size_bytes=item.get("size"),
                    sha256=item.get("sha256"),
                    file_type=package_type.value,
                    detected_platform=detect_platform(filename) or "macos",
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
        return {"source": "homebrew", "token": repository.external_id}

    async def health_check(self) -> ConnectorHealth:
        started = datetime.now()
        try:
            await self._get("/formula/wget.json")
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

    # --- Helpers ------------------------------------------------------------------------

    def _summary_to_repository(self, item: dict[str, Any], kind: str) -> RepositorySchema:
        token = str(item.get("name") or item.get("token") or "")
        homepage = item.get("homepage") or f"{self.base_url}/formula/{token}"
        return RepositorySchema(
            external_id=token,
            full_name=f"homebrew/{token}",
            name=token,
            description=item.get("desc"),
            homepage=homepage,
            html_url=homepage,
            api_url=f"{self.api_url}/{kind}/{token}.json",
            status=RepositoryStatus.ACTIVE,
            visibility=RepositoryVisibility.PUBLIC,
            license_spdx=self._license_to_spdx(item.get("license")),
            topics=[f"kind:{kind}"],
            source_type=self.source_type,
        )

    def _detail_to_repository(self, item: dict[str, Any]) -> RepositorySchema:
        kind = str(item.get("omni_kind", "formula"))
        token = str(item.get("name") or item.get("token") or "")
        homepage = item.get("homepage") or f"{self.base_url}/formula/{token}"
        return RepositorySchema(
            external_id=token,
            full_name=f"homebrew/{token}",
            name=token,
            description=item.get("desc"),
            homepage=homepage,
            html_url=homepage,
            api_url=f"{self.api_url}/{kind}/{token}.json",
            status=RepositoryStatus.ACTIVE,
            visibility=RepositoryVisibility.PUBLIC,
            license_spdx=self._license_to_spdx(item.get("license")),
            topics=[f"kind:{kind}"],
            source_type=self.source_type,
        )

    @staticmethod
    def _extract_asset_payloads(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Collect bottle/source (formula) or cask download payloads."""
        payloads: list[dict[str, Any]] = []
        if data.get("omni_kind") == "formula":
            bottle_root = data.get("bottle")
            if isinstance(bottle_root, dict):
                stable = bottle_root.get("stable") or {}
                files = stable.get("files") if isinstance(stable, dict) else {}
                for tag, info in (files or {}).items():
                    if isinstance(info, dict) and info.get("url"):
                        payloads.append(
                            {
                                "url": info["url"],
                                "kind": f"bottle-{tag}",
                                "sha256": info.get("sha256"),
                            }
                        )
            urls = data.get("urls") or {}
            stable_url = urls.get("stable") if isinstance(urls, dict) else None
            if isinstance(stable_url, dict) and stable_url.get("url"):
                payloads.append({"url": stable_url["url"], "kind": "source", "sha256": None})
        elif data.get("url"):
            payloads.append({"url": data["url"], "kind": "cask", "sha256": data.get("sha256")})
        return payloads

    @staticmethod
    def _license_to_spdx(license_value: Any) -> str | None:
        """Homebrew licenses are SPDX strings or clause lists like {'all_of': [...]}."""
        if license_value is None:
            return None
        if isinstance(license_value, str):
            return license_value
        if isinstance(license_value, list):
            flat: list[str] = []
            for entry in license_value:
                if isinstance(entry, dict):
                    for key in ("all_of", "any_of"):
                        clause = entry.get(key)
                        if isinstance(clause, list):
                            flat.extend(str(p) for p in clause)
                elif entry is not None:
                    flat.append(str(entry))
            return " OR ".join(flat) if flat else None
        return None
