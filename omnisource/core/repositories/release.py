"""Release repository for OmniSource."""

from uuid import UUID

from sqlalchemy import select

from omnisource.core.models.release import Release, ReleaseAsset
from omnisource.core.repositories.base import BaseRepository


class ReleaseRepository(BaseRepository[Release]):
    """Repository for release entities."""

    model = Release

    async def get_by_external_id(self, repository_id: UUID, external_id: str) -> Release | None:
        """Get a release by repository and external identifier."""
        result = await self.session.execute(
            select(Release).where(
                Release.repository_id == repository_id,
                Release.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_repository(self, repository_id: UUID, limit: int = 100) -> list[Release]:
        """List releases for a repository, newest first."""
        query = (
            select(Release)
            .where(Release.repository_id == repository_id)
            .order_by(Release.published_at.desc().nulls_last())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_latest_for_repository(self, repository_id: UUID) -> Release | None:
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
    ) -> tuple[Release, bool]:
        """Create or update a release; returns (release, created).

        The ``created`` flag lets callers push notifications for new releases.
        """
        release = await self.get_by_external_id(repository_id, external_id)
        created = release is None
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
        return release, created

    async def link_asset(
        self, release_id: UUID, asset_id: UUID, sort_order: int = 0
    ) -> ReleaseAsset:
        """Link an asset to a release (idempotent on re-sync)."""
        result = await self.session.execute(
            select(ReleaseAsset).where(
                ReleaseAsset.release_id == release_id,
                ReleaseAsset.asset_id == asset_id,
            )
        )
        release_asset = result.scalar_one_or_none()
        if release_asset is None:
            release_asset = ReleaseAsset(
                release_id=release_id, asset_id=asset_id, sort_order=sort_order
            )
            self.session.add(release_asset)
            await self.session.flush()
        return release_asset
