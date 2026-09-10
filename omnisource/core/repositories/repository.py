"""Repository repository for OmniSource."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from omnisource.core.models.repository import Repository, RepositoryMetadata
from omnisource.core.repositories.base import BaseRepository


class RepositoryRepository(BaseRepository[Repository]):
    """Repository for software repository entities."""

    model = Repository

    async def get_by_external_id(self, source_id: UUID, external_id: str) -> Repository | None:
        """Get a repository by source and external identifier."""
        result = await self.session.execute(
            select(Repository).where(
                Repository.source_id == source_id,
                Repository.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_full_name(self, full_name: str) -> Repository | None:
        """Get a repository by full name (owner/repo)."""
        result = await self.session.execute(
            select(Repository).where(Repository.full_name == full_name)
        )
        return result.scalar_one_or_none()

    async def list_repositories(
        self,
        source_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Repository]:
        """List repositories, optionally filtered by source."""
        query = select(Repository).options(selectinload(Repository.metadata_obj))
        if source_id is not None:
            query = query.where(Repository.source_id == source_id)
        query = query.order_by(Repository.updated_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def upsert_repository(
        self,
        source_id: UUID,
        external_id: str,
        values: dict,
    ) -> Repository:
        """Create or update a repository identified by source + external id."""
        repository = await self.get_by_external_id(source_id, external_id)
        if repository is None:
            repository = Repository(source_id=source_id, external_id=external_id, **values)
            self.session.add(repository)
            await self.session.flush()
        else:
            for key, value in values.items():
                if hasattr(repository, key):
                    setattr(repository, key, value)
            await self.session.flush()
        return repository

    async def upsert_metadata(self, repository_id: UUID, values: dict) -> RepositoryMetadata:
        """Create or update metadata for a repository."""
        result = await self.session.execute(
            select(RepositoryMetadata).where(RepositoryMetadata.repository_id == repository_id)
        )
        metadata = result.scalar_one_or_none()
        if metadata is None:
            metadata = RepositoryMetadata(repository_id=repository_id, **values)
            self.session.add(metadata)
        else:
            for key, value in values.items():
                if hasattr(metadata, key):
                    setattr(metadata, key, value)
        await self.session.flush()
        return metadata
