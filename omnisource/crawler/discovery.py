"""Repository discovery and ingestion service."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.connectors.registry import create_connector
from omnisource.core.models.repository import (
    RepositoryStatus,
    RepositoryVisibility,
)
from omnisource.core.models.source import SourceType
from omnisource.core.repositories.repository import RepositoryRepository
from omnisource.core.repositories.source import SourceRepository
from omnisource.crawler.checkpoint import Checkpoint
from omnisource.crawler.filters import RepositoryFilter
from omnisource.crawler.policies import ProcessingPolicies
from omnisource.processing.metadata_extractor import MetadataExtractor

logger = get_logger(__name__)


class DiscoveryService:
    """Discovers repositories from sources and persists them to the database."""

    def __init__(
        self,
        session: AsyncSession,
        policies: ProcessingPolicies | None = None,
    ):
        self.session = session
        self.policies = policies or ProcessingPolicies.from_settings()

    async def discover(
        self,
        source_type: str = "github",
        query: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Run a discovery pass for a source type."""
        source_repo = SourceRepository(self.session)
        source = await source_repo.get_by_type(SourceType(source_type))
        if source is None:
            source = await source_repo.ensure_default(
                name=source_type.title(),
                source_type=SourceType(source_type),
                base_url=f"https://{source_type}.com",
                api_url=None,
                is_active=True,
            )
            await self.session.commit()

        connector = create_connector(source_type)
        await connector.initialize()

        batch = limit or self.policies.batch_size

        try:
            checkpoint = await Checkpoint(self.session, source.id).load()
            cursor = checkpoint.cursor

            repositories, page_info = await connector.discover(
                query=query, cursor=cursor, limit=batch
            )

            repo_filter = RepositoryFilter(
                min_stars=self.policies.min_stars,
                exclude_forks=True,
                exclude_archived=True,
            )

            raw_items = [r.model_dump() for r in repositories]
            filtered = repo_filter.apply(raw_items)

            repository_repo = RepositoryRepository(self.session)
            metadata_extractor = MetadataExtractor()

            ingested = 0
            for item in filtered:
                await self._ingest_repository(repository_repo, metadata_extractor, source.id, item)
                ingested += 1

            await checkpoint.save(
                cursor=page_info.next_cursor,
                discovered=len(repositories),
                updated=ingested,
                failed=len(repositories) - ingested,
            )
            await self.session.commit()

            return {
                "source": source_type,
                "discovered": len(repositories),
                "ingested": ingested,
                "filtered_out": len(repositories) - len(filtered),
                "next_cursor": page_info.next_cursor,
                "has_next": page_info.has_next,
            }
        except Exception:
            await self.session.rollback()
            raise
        finally:
            await connector.close()

    async def _ingest_repository(
        self,
        repository_repo: RepositoryRepository,
        extractor: MetadataExtractor,
        source_id,
        item: dict[str, Any],
    ) -> None:
        """Persist a single repository record and its metadata."""
        status = item.get("status")
        visibility = item.get("visibility")
        if isinstance(status, str):
            status = RepositoryStatus(status)
        else:
            status = RepositoryStatus.ACTIVE
        if isinstance(visibility, str):
            visibility = RepositoryVisibility(visibility)
        else:
            visibility = RepositoryVisibility.PUBLIC

        values = {
            "full_name": item.get("full_name") or item.get("name") or "",
            "name": item.get("name") or item.get("full_name", "").split("/")[-1] or "",
            "description": item.get("description"),
            "homepage": item.get("homepage"),
            "html_url": item.get("html_url") or "",
            "api_url": item.get("api_url"),
            "status": status,
            "visibility": visibility,
            "is_fork": bool(item.get("is_fork")),
            "is_archived": bool(item.get("is_archived")),
            "stars": int(item.get("stars") or 0),
            "forks": int(item.get("forks") or 0),
            "open_issues": int(item.get("open_issues") or 0),
            "size_kb": int(item.get("size_kb") or 0),
            "language": item.get("language"),
            "default_branch": item.get("default_branch"),
            "created_at_external": item.get("created_at_external"),
            "updated_at_external": item.get("updated_at_external"),
            "pushed_at": item.get("pushed_at"),
        }

        repository = await repository_repo.upsert_repository(
            source_id=source_id,
            external_id=str(item.get("external_id") or item.get("full_name") or ""),
            values=values,
        )

        metadata_values = {
            "topics": item.get("topics") or [],
            "license_spdx": item.get("license_spdx"),
        }
        await repository_repo.upsert_metadata(repository.id, metadata_values)
