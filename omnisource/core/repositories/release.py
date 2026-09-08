"""Release repository for OmniSource."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.core.models.release import Release, ReleaseAsset
from omnisource.core.repositories.base import BaseRepository


class ReleaseRepository(BaseRepository[Release]):
    """Repository for release entities."""

    model = Release

    async def get_by_external_id(
        self, repository_id: UUID, external_id: str
    ) -> Optional[Release]:
        """Get a release by repository and external identifier."""
        result = await self.session.execute(
            select(Release).where(
                Release.repository_id == repository_id,
                Release.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_repository(
        self, repository_id: UUID, limit: int = 100
    ) -> List[Release]:
        """List releases for a repository, newest first."""
        query = (
            select(Release)
            .where(Release.repository_id == repository_id)
            .order_by(Release.published_at.desc().nulls_last())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_latest_for_repository(
        self, repository_id: UUID
    ) -> Optional[Release]:
        """Get the latest non-draft release for a repository."""
        result = await self.session.execute(
            select(Release)
            .where(
                Release.repository_id == repository_id,
                Release.is_draft.is_(False),
            )
            .order_by(Release.published_at.desc().nulls_last())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def upsert_release(
        self,
        application_id: UUID,
        repository_id: UUID,
        external_id: str,
        values: dict,
    ) -> Release:
        """Create or update a release identified by repository + external id."""
        release = await self.get_by_external_id(repository_id, external_id)
        if release is None:
            release = Release(
                application_id=application_id,
                repository_id=repository_id,
                external_id=external_id,
                **values,
            )
            self.session.add(release)
        else:
            for key, value in values.items():
                if hasattr(release, key):
                    setattr(release, key, value)
        await self.session.flush()
        return release

    async def link_asset(
        self, release_id: UUID, asset_id: UUID, sort_order: int = 0
    ) -> ReleaseAsset:
        """Link an asset to a release."""
        release_asset = ReleaseAsset(
            release_id=release_id, asset_id=asset_id, sort_order=sort_order
        )
        self.session.add(release_asset)
        await self.session.flush()
        return release_asset
