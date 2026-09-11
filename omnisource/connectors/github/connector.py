"""
GitHub connector implementation for OmniSource.
"""

from datetime import datetime, timedelta
from typing import Any

from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings
from omnisource.connectors.base import (
    ConnectorError,
    ConnectorHealth,
    PageInfo,
    SourceConnector,
)
from omnisource.connectors.cache import ResponseCache
from omnisource.connectors.github.client import GitHubClient
from omnisource.connectors.rate_limiter import RateLimiter
from omnisource.core.schemas.asset import AssetSchema, AssetSourceSchema, AssetStatusSchema
from omnisource.core.schemas.release import ReleaseSchema, ReleaseStatusSchema
from omnisource.core.schemas.repository import RepositorySchema

logger = get_logger(__name__)


class GitHubConnector(SourceConnector):
    """
    GitHub connector for OmniSource.

    Implements the SourceConnector interface for GitHub API.
    """

    source_name = "github"
    source_type = "github"
    base_url = "https://github.com"
    api_url = "https://api.github.com"

    def __init__(
        self,
        token: str | None = None,
        rate_limiter: RateLimiter | None = None,
        cache: ResponseCache | None = None,
    ):
        """
        Initialize the GitHub connector.

        Args:
            token: GitHub personal access token
            rate_limiter: Rate limiter instance
            cache: Response cache instance
        """
        super().__init__()
        self.token = token or get_settings().github.GH_TOKEN
        self.rate_limiter = rate_limiter or RateLimiter(
            max_requests=get_settings().github.GH_RATE_LIMIT,
            period=timedelta(hours=1),
        )
        self.cache = cache or ResponseCache()
        self._client: GitHubClient | None = None

    async def initialize(self) -> None:
        """Initialize the connector."""
        self._client = GitHubClient(
            token=self.token,
            rate_limiter=self.rate_limiter,
            cache=self.cache,
        )
        await self._client.initialize()
        self._initialized = True
        logger.info("GitHub connector initialized")

    async def close(self) -> None:
        """Close the connector."""
        if self._client:
            await self._client.close()
            self._client = None
        self._initialized = False
        logger.info("GitHub connector closed")

    async def discover(
        self, query: str | None = None, cursor: str | None = None, limit: int = 100, **kwargs: Any
    ) -> tuple[list[RepositorySchema], PageInfo]:
        """
        Discover repositories from GitHub.

        Args:
            query: Search query
            cursor: Pagination cursor
            limit: Maximum repositories to return
            **kwargs: Additional parameters

        Returns:
            Tuple of (repositories, page_info)
        """
        if not self._client:
            raise ConnectorError("Connector not initialized", is_retriable=False)

        # Build search query
        search_query = query or self._build_default_query()

        # Get page from cursor if available
        page = 1
        if cursor:
            try:
                page = int(cursor)
            except ValueError:
                page = 1

        # Search repositories
        try:
            result = await self._client.search_repositories(
                query=search_query,
                sort="updated",
                order="desc",
                per_page=min(limit, 100),  # GitHub max per_page is 100
            )
        except Exception as e:
            logger.error(f"Failed to discover repositories: {e}")
            raise ConnectorError(f"Discovery failed: {e}", is_retriable=True) from e

        # Convert to RepositorySchema
        repositories: list[RepositorySchema] = []
        for item in result.get("items", []):
            try:
                repo_schema = await self._convert_to_repository_schema(item)
                repositories.append(repo_schema)
            except Exception as e:
                logger.warning(f"Failed to convert repository {item.get('id')}: {e}")
                continue

        # Update stats
        self.update_stats(
            requests=self._stats.requests + 1,
            successes=self._stats.successes + 1,
            repositories_discovered=self._stats.repositories_discovered + len(repositories),
        )

        # Build page info
        total_count = result.get("total_count", 0)
        page_info = PageInfo(
            page=page,
            per_page=min(limit, 100),
            total=total_count,
            total_pages=(total_count + 99) // 100,  # Calculate total pages
            has_next=page * 100 < total_count,
            has_previous=page > 1,
            next_cursor=str(page + 1) if page * 100 < total_count else None,
            prev_cursor=str(page - 1) if page > 1 else None,
        )

        return repositories, page_info

    def _build_default_query(self) -> str:
        """Build default search query for discovery."""
        # Look for repositories with:
        # - Some stars (but not too many to avoid huge projects)
        # - Recent activity
        # - Open source licenses
        # - Releases
        query_parts = [
            "is:public",
            "archived:false",
            "pushed:>2024-01-01",  # Active in the last year
        ]

        # Add star range (avoid very small and very large repos)
        query_parts.append("stars:10..10000")

        # Add license filter (common open source licenses)
        licenses = ["MIT", "Apache", "GPL", "BSD", "AGPL", "LGPL", "MPL", "ISC", "Unlicense"]
        query_parts.append(f"license:{','.join(licenses)}")

        return " ".join(query_parts)

    async def get_repository(self, repository_id: str, **kwargs: Any) -> RepositorySchema:
        """
        Get details for a specific repository.

        Args:
            repository_id: Repository identifier (format: "owner/repo")
            **kwargs: Additional parameters

        Returns:
            Repository schema
        """
        if not self._client:
            raise ConnectorError("Connector not initialized", is_retriable=False)

        # Parse repository_id
        if "/" not in repository_id:
            raise ConnectorError(f"Invalid repository ID format: {repository_id}")

        owner, repo = repository_id.split("/", 1)

        try:
            data = await self._client.get_repository(owner, repo)
            return await self._convert_to_repository_schema(data)
        except Exception as e:
            logger.error(f"Failed to get repository {repository_id}: {e}")
            raise ConnectorError(f"Failed to get repository: {e}", is_retriable=True) from e

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
        if not self._client:
            raise ConnectorError("Connector not initialized", is_retriable=False)

        # Parse repository ID (full_name "owner/repo" preferred; a numeric
        # external_id alone cannot address a repository endpoint)
        owner, repo = self._parse_repository_id(repository.full_name or repository.external_id)

        try:
            releases_data = await self._client.get_releases(owner, repo)
            releases: list[ReleaseSchema] = []

            for release_data in releases_data:
                try:
                    release_schema = await self._convert_to_release_schema(release_data, repository)
                    releases.append(release_schema)
                except Exception as e:
                    logger.warning(f"Failed to convert release {release_data.get('id')}: {e}")
                    continue

            # Sort by published_at descending
            releases.sort(key=lambda r: r.published_at or datetime.min, reverse=True)

            return releases
        except Exception as e:
            logger.error(f"Failed to get releases for {repository.full_name}: {e}")
            raise ConnectorError(f"Failed to get releases: {e}", is_retriable=True) from e

    async def get_assets(self, release: ReleaseSchema, **kwargs: Any) -> list[AssetSchema]:
        """
        Get assets for a release.

        Args:
            release: Release schema
            **kwargs: Additional parameters

        Returns:
            List of asset schemas
        """
        # Assets are already included in the release data from GitHub
        # So we just need to convert them
        assets: list[AssetSchema] = []

        for asset_data in release.assets or []:
            try:
                asset_schema = await self._convert_to_asset_schema(asset_data, release)
                assets.append(asset_schema)
            except Exception as e:
                logger.warning(f"Failed to convert asset {asset_data.get('id')}: {e}")
                continue

        return assets

    async def get_metadata(self, repository: RepositorySchema, **kwargs: Any) -> dict[str, Any]:
        """
        Get metadata for a repository.

        Args:
            repository: Repository schema
            **kwargs: Additional parameters

        Returns:
            Metadata dictionary
        """
        if not self._client:
            raise ConnectorError("Connector not initialized", is_retriable=False)

        owner, repo = self._parse_repository_id(repository.full_name or repository.external_id)

        metadata: dict[str, Any] = {}

        # Get README
        try:
            readme = await self._client.get_readme(owner, repo)
            if readme:
                metadata["readme"] = readme
        except Exception as e:
            logger.debug(f"Failed to get README for {repository.full_name}: {e}")

        # Get license
        try:
            license_data = await self._client.get_license(owner, repo)
            if license_data:
                metadata["license"] = license_data
        except Exception as e:
            logger.debug(f"Failed to get license for {repository.full_name}: {e}")

        # Get topics
        try:
            topics = await self._client.get_topics(owner, repo)
            metadata["topics"] = topics
        except Exception as e:
            logger.debug(f"Failed to get topics for {repository.full_name}: {e}")

        # Get languages
        try:
            languages = await self._client.get_languages(owner, repo)
            metadata["languages"] = languages
        except Exception as e:
            logger.debug(f"Failed to get languages for {repository.full_name}: {e}")

        # Get contributors
        try:
            contributors = await self._client.get_contributors(owner, repo)
            metadata["contributors"] = contributors
        except Exception as e:
            logger.debug(f"Failed to get contributors for {repository.full_name}: {e}")

        # Extract conventional metadata files without assuming they exist.
        try:
            contents = await self._client.get_contents(owner, repo)
            files = [
                str(item.get("name"))
                for item in contents
                if isinstance(item, dict) and item.get("name")
            ]
            metadata["files"] = files
            lower_files = {filename.lower(): filename for filename in files}
            for name in ("changelog.md", "changes.md", "history.md"):
                if path := lower_files.get(name):
                    changelog = await self._client.get_file_text(owner, repo, path)
                    if changelog:
                        metadata["changelog"] = changelog
                        break
        except Exception as e:
            logger.debug(f"Failed to get file inventory for {repository.full_name}: {e}")

        return metadata

    async def health_check(self) -> ConnectorHealth:
        """
        Check the health of the connector.

        Returns:
            Health status
        """
        try:
            start_time = datetime.now()

            if self._client is None:
                await self.initialize()
            if self._client is None:  # pragma: no cover - defensive
                raise ConnectorError("HTTP client failed to initialize", is_retriable=False)

            # Make a test request
            await self._client.get("/")

            latency = (datetime.now() - start_time).total_seconds() * 1000

            self.update_health(
                healthy=True,
                latency_ms=latency,
                last_check=datetime.now(),
                last_success=datetime.now(),
                last_error=None,
            )

            return self._health
        except Exception as e:
            self.update_health(
                healthy=False,
                last_check=datetime.now(),
                last_error=str(e),
            )
            logger.error(f"GitHub health check failed: {e}")
            return self._health

    def _parse_repository_id(self, repo_id: str) -> tuple[str, str]:
        """Parse repository ID to owner and repo."""
        if "/" in repo_id:
            parts = repo_id.split("/", 1)
            return parts[0], parts[1]
        return repo_id, repo_id

    async def _convert_to_repository_schema(self, data: dict[str, Any]) -> RepositorySchema:
        """Convert GitHub API response to RepositorySchema."""
        from omnisource.core.models.source import SourceType
        from omnisource.core.schemas.repository import RepositoryStatus, RepositoryVisibility

        # Get owner info
        data.get("owner", {})

        return RepositorySchema(
            external_id=str(data.get("id", "")),
            full_name=data.get("full_name", ""),
            name=data.get("name", ""),
            description=data.get("description"),
            homepage=data.get("homepage"),
            html_url=data.get("html_url", ""),
            api_url=data.get("url", ""),
            status=RepositoryStatus.ACTIVE
            if not data.get("archived", False)
            else RepositoryStatus.ARCHIVED,
            visibility=RepositoryVisibility.PUBLIC
            if not data.get("private", False)
            else RepositoryVisibility.PRIVATE,
            is_fork=data.get("fork", False),
            is_archived=data.get("archived", False),
            stars=data.get("stargazers_count", 0),
            forks=data.get("forks_count", 0),
            open_issues=data.get("open_issues_count", 0),
            size_kb=data.get("size", 0),
            language=data.get("language"),
            default_branch=data.get("default_branch", "main"),
            created_at_external=self._parse_datetime(data.get("created_at")),
            updated_at_external=self._parse_datetime(data.get("updated_at")),
            pushed_at=self._parse_datetime(data.get("pushed_at")),
            license_spdx=data.get("license", {}).get("spdx_id") if data.get("license") else None,
            topics=data.get("topics", []),
            source_type=SourceType.GITHUB,
        )

    async def _convert_to_release_schema(
        self,
        data: dict[str, Any],
        repository: RepositorySchema,
    ) -> ReleaseSchema:
        """Convert GitHub API response to ReleaseSchema."""
        return ReleaseSchema(
            external_id=str(data.get("id", "")),
            version=data.get("tag_name", data.get("name", "")),
            tag=data.get("tag_name"),
            name=data.get("name"),
            body=data.get("body"),
            status=ReleaseStatusSchema.RELEASED
            if not data.get("draft", False)
            else ReleaseStatusSchema.DRAFT,
            is_prerelease=data.get("prerelease", False),
            is_draft=data.get("draft", False),
            published_at=self._parse_datetime(data.get("published_at")),
            created_at_external=self._parse_datetime(data.get("created_at")),
            commit_sha=data.get("target_commitish", ""),
            tarball_url=data.get("tarball_url"),
            zipball_url=data.get("zipball_url"),
            download_count=data.get("download_count", 0),
            repository_id=repository.id,
            assets=data.get("assets", []),
        )

    async def _convert_to_asset_schema(
        self,
        data: dict[str, Any],
        release: ReleaseSchema,
    ) -> AssetSchema:
        """Convert GitHub asset to AssetSchema."""
        from omnisource.core.models.release import detect_architecture, detect_platform

        filename = data.get("name", "")

        # Detect platform and architecture
        detected_platform = detect_platform(filename)
        detected_architecture = detect_architecture(filename)

        # Map content_type to mime_type
        mime_type = data.get("content_type", "application/octet-stream")

        # Map package type
        package_type = self._map_package_type(filename, mime_type)

        return AssetSchema(
            asset_id=f"gh-{data.get('id', '')}",
            filename=filename,
            display_name=data.get("label", filename),
            download_url=data.get("browser_download_url", data.get("url", "")),
            size_bytes=data.get("size", 0),
            mime_type=mime_type,
            file_type=package_type,
            detected_platform=detected_platform,
            detected_architecture=detected_architecture,
            platform_confidence=0.8 if detected_platform else 0.0,
            architecture_confidence=0.8 if detected_architecture else 0.0,
            package_type=package_type,
            version=release.version,
            sha256=None,  # Will be calculated during validation
            sha512=None,
            source=AssetSourceSchema.GITHUB_RELEASE,
            status=AssetStatusSchema.PENDING,
            download_count=data.get("download_count", 0),
            release_id=release.id,
        )

    def _map_package_type(self, filename: str, mime_type: str) -> str:
        """Map filename and mime type to package type."""
        from omnisource.core.models.release import PackageType

        filename_lower = filename.lower()

        # Check by extension
        if filename_lower.endswith(".apk"):
            return PackageType.APK.value
        elif filename_lower.endswith(".aab"):
            return PackageType.AAB.value
        elif filename_lower.endswith(".ipa"):
            return PackageType.IPA.value
        elif filename_lower.endswith(".exe"):
            return PackageType.EXE.value
        elif filename_lower.endswith(".msi"):
            return PackageType.MSI.value
        elif filename_lower.endswith(".msix"):
            return PackageType.MSIX.value
        elif filename_lower.endswith(".appx"):
            return PackageType.APPX.value
        elif filename_lower.endswith(".dmg"):
            return PackageType.DMG.value
        elif filename_lower.endswith(".pkg"):
            return PackageType.PKG.value
        elif filename_lower.endswith(".deb"):
            return PackageType.DEB.value
        elif filename_lower.endswith(".rpm"):
            return PackageType.RPM.value
        elif filename_lower.endswith(".flatpak"):
            return PackageType.FLATPAK.value
        elif filename_lower.endswith(".flatpakref"):
            return PackageType.FLATPAKREF.value
        elif filename_lower.endswith(".appimage"):
            return PackageType.APPIMAGE.value
        elif filename_lower.endswith(".zip"):
            return PackageType.ZIP.value
        elif filename_lower.endswith(".tar.gz") or filename_lower.endswith(".tgz"):
            return PackageType.TAR_GZ.value
        elif filename_lower.endswith(".tar.xz"):
            return PackageType.TAR_XZ.value
        elif filename_lower.endswith(".snap"):
            return PackageType.SNAP.value

        # Check by mime type
        if mime_type == "application/vnd.android.package-archive":
            return PackageType.APK.value
        elif mime_type == "application/x-msdownload":
            return PackageType.EXE.value
        elif mime_type == "application/x-msi":
            return PackageType.MSI.value
        elif mime_type == "application/x-apple-diskimage":
            return PackageType.DMG.value
        elif mime_type == "application/vnd.debian.binary-package":
            return PackageType.DEB.value
        elif mime_type == "application/x-rpm":
            return PackageType.RPM.value
        elif mime_type == "application/x-flatpak":
            return PackageType.FLATPAK.value

        return PackageType.BINARY.value

    def _parse_datetime(self, value: Any) -> datetime | None:
        """Parse datetime from various formats."""
        if value is None:
            return None

        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return None
