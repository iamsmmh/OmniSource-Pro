"""Checkpoint persistence and resumption for ingestion."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.core.repositories.sync import SyncRepository

if TYPE_CHECKING:
    from omnisource.core.models.sync import SyncState


class Checkpoint:
    """Tracks and persists ingestion progress for resumable discovery."""

    def __init__(
        self, session: AsyncSession, source_id: UUID | None, repository_id: UUID | None = None
    ):
        self._repo = SyncRepository(session)
        self.source_id = source_id
        self.repository_id = repository_id
        self._state: SyncState | None = None

    async def load(self) -> "Checkpoint":
        """Load (or create) the persisted sync state."""
        self._state = await self._repo.get_or_create_sync_state(
            source_id=self.source_id,
            repository_id=self.repository_id,
        )
        return self

    @property
    def cursor(self) -> str | None:
        return self._state.cursor if self._state else None

    @property
    def etag(self) -> str | None:
        return self._state.etag if self._state else None

    @property
    def state(self) -> "SyncState | None":
        return self._state

    async def save(
        self,
        cursor: str | None = None,
        etag: str | None = None,
        discovered: int | None = None,
        updated: int | None = None,
        failed: int | None = None,
        error: str | None = None,
    ) -> None:
        """Persist progress updates."""
        if self._state is None:
            await self.load()
        if self._state is None:  # pragma: no cover - defensive
            raise RuntimeError("Checkpoint state failed to load")

        values: dict[str, Any] = {
            "last_attempt": datetime.now(UTC),
        }
        if cursor is not None:
            values["cursor"] = cursor
        if etag is not None:
            values["etag"] = etag
        if error is not None:
            values["last_error"] = error[:500]
        else:
            values["last_success"] = datetime.now(UTC)

        if discovered is not None:
            self._state.discovered_count = self._state.discovered_count + discovered
        if updated is not None:
            self._state.updated_count = self._state.updated_count + updated
        if failed is not None:
            self._state.failed_count = self._state.failed_count + failed

        await self._repo.update_sync_state(self._state, **values)
        await self._repo.session.commit()


__all__ = ["Checkpoint"]
