"""Winget connector for OmniSource.

The Windows Package Manager community repository (``microsoft/winget-pkgs``)
is a plain GitHub repository of YAML manifests. Rather than requiring the
authenticated Microsoft REST source, this connector reads the public manifest
tree through the GitHub API:

- ``GET /repos/microsoft/winget-pkgs/contents/manifests/{letter}``
  → publisher folders (discovery)
- ``GET /repos/microsoft/winget-pkgs/contents/manifests/{p}/{Publisher}/{App}/``
  → version folders (latest = release)
- Raw manifest files are fetched from raw.githubusercontent.com and parsed
  with a minimal YAML field reader (no pyyaml dependency).

Only lightweight, regex-based extraction of the fields OmniSource needs is
performed (PackageIdentifier, PackageVersion, Publisher, PackageName,
License, Homepage, InstallerUrl, InstallerSha256).
"""

import re
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
from omnisource.core.models.release import detect_architecture, detect_package_type, detect_platform
from omnisource.core.schemas.asset import AssetSchema, AssetSourceSchema, AssetStatusSchema
from omnisource.core.schemas.release import ReleaseSchema, ReleaseStatusSchema
from omnisource.core.schemas.repository import (
    RepositorySchema,
    RepositoryStatus,
    RepositoryVisibility,
)

logger = get_logger(__name__)

_USER_AGENT = "OmniSource/0.1.0"
_REPO_API = "https://api.github.com/repos/microsoft/winget-pkgs/contents"
_RAW_BASE = "https://raw.githubusercontent.com/microsoft/winget-pkgs/master"

_LETTERS = [chr(c) for c in range(ord("a"), ord("z") + 1)]


def _extract_scalar(yaml_text: str, field: str) -> str | None:
    """Extract a top-level scalar field from a small winget YAML manifest."""
    match = re.search(
        rf"^[ \t]*-?[ \t]*{re.escape(field)}\s*:\s*[\'\"]?(.+?)[\'\"]?\s*$",
        yaml_text,
        re.MULTILINE,
    )
    return match.group(1).strip() if match else None


def _extract_sequence(yaml_text: str, field: str) -> list[str]:
    match = re.search(
        rf"^\s*{re.escape(field)}\s*:\s*$\n((?:\s+-\s+.*\n?)*)", yaml_text, re.MULTILINE
    )
    if not match:
        return []
    return [
        line.strip().lstrip("- ").strip().strip("\"'")
        for line in match.group(1).splitlines()
        if line.strip()
    ]


class WingetConnector(SourceConnector):
    """Winget (winget-pkgs manifest repository) connector."""

    source_name = "winget"
    source_type = "winget"
    base_url = "https://github.com/microsoft/winget-pkgs"
    api_url = _REPO_API

    def __init__(self, rate_limiter: RateLimiter | None = None) -> None:
        super().__init__()
        self.rate_limiter = rate_limiter or RateLimiter(
            max_requests=60,
            period=timedelta(minutes=1),  # unauthenticated GitHub
        )
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": _USER_AGENT}
        self._client = httpx.AsyncClient(headers=headers, timeout=30.0)
        self._initialized = True
        logger.info("Winget connector initialized")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._initialized = False

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ConnectorError("Winget connector not initialized", is_retriable=False)
        return self._client

    async def _get_json(self, url: str) -> Any:
        client = self._require_client()
        response = await get_with_retry(client, url, limiter=self.rate_limiter)
        if response.status_code == 404:
            raise ConnectorError(f"Not found: {url}", error_code="HTTP_404")
        if response.status_code == 403:
            raise ConnectorError("Winget GitHub API rate limited", error_code="RATE_LIMIT")
        response.raise_for_status()
        return response.json()

    async def _get_text(self, url: str) -> str:
        client = self._require_client()
        response = await get_with_retry(client, url, limiter=self.rate_limiter)
        if response.status_code == 404:
            raise ConnectorError(f"Not found: {url}", error_code="HTTP_404")
        response.raise_for_status()
        return response.text

    # --- Interface -----------------------------------------------------------------

    async def discover(
        self,
        query: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
        **kwargs: Any,
    ) -> tuple[list[RepositorySchema], PageInfo]:
        """Discover winget packages by walking publisher-letter folders.

        Cursor format: ``{letter}:{offset}``.
        """
        letter, offset = "a", 0
        if cursor and ":" in cursor:
            raw_letter, raw_offset = cursor.split(":", 1)
            if raw_letter in _LETTERS:
                letter = raw_letter
            try:
                offset = max(0, int(raw_offset))
            except ValueError:
                offset = 0

        publishers = await self._get_json(f"{_REPO_API}/manifests/{letter}")
        if not isinstance(publishers, list):
            raise ConnectorError("Unexpected winget manifests payload", is_retriable=False)

        repositories: list[RepositorySchema] = []
        remaining = limit
        publisher_list = [p for p in publishers if p.get("type") == "dir"]
        idx = offset

        while len(repositories) < limit and idx < len(publisher_list):
            publisher_path = publisher_list[idx].get("path", "")
            idx += 1
            try:
                packages = await self._get_json(f"{_REPO_API}/{publisher_path}")
            except ConnectorError as exc:
                logger.warning("Skipping winget publisher %s: %s", publisher_path, exc)
                continue
            for package in packages or []:
                if package.get("type") != "dir" or remaining <= 0:
                    continue
                package_id = str(package.get("name", "")).replace("_", " ")
                if query and query.lower() not in package_id.lower():
                    continue
                repositories.append(
                    RepositorySchema(
                        external_id=package_id,
                        full_name=str(package.get("path", "")).removeprefix("manifests/"),
                        name=package_id,
                        description=None,
                        homepage=f"{self.base_url}/tree/master/{package.get('path', '')}",
                        html_url=f"{self.base_url}/tree/master/{package.get('path', '')}",
                        api_url=f"{_REPO_API}/{package.get('path', '')}",
                        status=RepositoryStatus.ACTIVE,
                        visibility=RepositoryVisibility.PUBLIC,
                        source_type=self.source_type,
                    )
                )
                remaining -= 1

        next_cursor = None
        has_next = False
        if idx < len(publisher_list):
            next_cursor = f"{letter}:{idx}"
            has_next = True
        elif letter in _LETTERS and _LETTERS.index(letter) < len(_LETTERS) - 1:
            next_cursor = f"{_LETTERS[_LETTERS.index(letter) + 1]}:0"
            has_next = True

        page_info = PageInfo(
            page=offset + 1,
            per_page=limit,
            total=len(repositories),
            has_next=has_next,
            has_previous=offset > 0 or _LETTERS.index(letter) > 0,
            next_cursor=next_cursor,
        )
        return repositories, page_info

    async def _fetch_latest_manifest(self, package_id: str) -> dict[str, Any]:
        """Return {path, yaml} for the latest version manifest of a package."""
        client = self._require_client()
        response = await get_with_retry(
            client,
            f"{_REPO_API}/manifests/{package_id.replace(' ', '_')}",
            limiter=self.rate_limiter,
        )
        if response.status_code == 404:
            raise ConnectorError(f"Winget package not found: {package_id}", error_code="HTTP_404")
        response.raise_for_status()
        versions = response.json()
        if not isinstance(versions, list) or not versions:
            raise ConnectorError(f"Winget package has no versions: {package_id}")

        latest = max(
            (v for v in versions if v.get("type") == "dir"),
            key=lambda v: str(v.get("name", "")),
            default=None,
        )
        if latest is None:
            raise ConnectorError(f"Winget package has no version dirs: {package_id}")

        manifest_path = str(latest.get("path", ""))
        yaml_text = await self._get_text(
            f"{_RAW_BASE}/{manifest_path}/{package_id.replace(' ', '_')}.yaml"
        )
        return {"path": manifest_path, "yaml": yaml_text}

    async def get_repository(self, repository_id: str, **kwargs: Any) -> RepositorySchema:
        """Fetch the latest version manifest for a package id."""
        manifest = await self._fetch_latest_manifest(repository_id)
        return self._manifest_to_repository(manifest["yaml"], manifest["path"])

    async def get_releases(
        self, repository: RepositorySchema, **kwargs: Any
    ) -> list[ReleaseSchema]:
        manifest = await self._fetch_latest_manifest(repository.external_id)
        yaml_text = manifest["yaml"]
        version = _extract_scalar(yaml_text, "PackageVersion") or ""
        installer_url = _extract_scalar(yaml_text, "InstallerUrl")
        release = ReleaseSchema(
            external_id=f"winget-{repository.external_id}-{version}",
            version=version,
            tag=version,
            name=f"{repository.name} {version}",
            body=None,
            status=ReleaseStatusSchema.RELEASED,
            repository_id=repository.id,
            assets=[
                {
                    "InstallerUrl": installer_url,
                    "InstallerSha256": _extract_scalar(yaml_text, "InstallerSha256"),
                }
            ]
            if installer_url
            else [],
        )
        return [release]

    async def get_assets(self, release: ReleaseSchema, **kwargs: Any) -> list[AssetSchema]:
        assets: list[AssetSchema] = []
        for item in release.assets or []:
            if not isinstance(item, dict) or not item.get("InstallerUrl"):
                continue
            url = str(item["InstallerUrl"])
            filename = url.rsplit("/", 1)[-1]
            package_type = detect_package_type(filename)
            assets.append(
                AssetSchema(
                    asset_id=f"winget-{item.get('InstallerSha256', filename)[:16]}",
                    filename=filename,
                    display_name=filename,
                    download_url=url,
                    size_bytes=None,
                    file_type=package_type.value,
                    detected_platform=detect_platform(filename) or "windows",
                    detected_architecture=detect_architecture(filename),
                    package_type=package_type.value,
                    sha256=item.get("InstallerSha256"),
                    version=release.version,
                    source=AssetSourceSchema.OFFICIAL,
                    status=AssetStatusSchema.PENDING,
                    release_id=release.id,
                )
            )
        return assets

    async def get_metadata(self, repository: RepositorySchema, **kwargs: Any) -> dict[str, Any]:
        return {"source": "winget", "package_identifier": repository.external_id}

    async def health_check(self) -> ConnectorHealth:
        started = datetime.now()
        try:
            await self._get_json(f"{_REPO_API}/manifests/0")
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

    def _manifest_to_repository(self, yaml_text: str, manifest_path: str) -> RepositorySchema:
        package_id = _extract_scalar(yaml_text, "PackageIdentifier") or manifest_path
        name = _extract_scalar(yaml_text, "PackageName") or package_id

        return RepositorySchema(
            external_id=package_id,
            full_name=manifest_path.removeprefix("manifests/"),
            name=name,
            description=_extract_scalar(yaml_text, "ShortDescription"),
            homepage=_extract_scalar(yaml_text, "PackageUrl")
            or _extract_scalar(yaml_text, "PublisherUrl"),
            html_url=f"{self.base_url}/tree/master/{manifest_path}",
            api_url=f"{_REPO_API}/{manifest_path}",
            status=RepositoryStatus.ACTIVE,
            visibility=RepositoryVisibility.PUBLIC,
            license_spdx=_extract_scalar(yaml_text, "License"),
            language=None,
            source_type=self.source_type,
        )
