"""Source repository for OmniSource."""

from sqlalchemy import select

from omnisource.core.models.source import Source, SourceHealth, SourceType
from omnisource.core.repositories.base import BaseRepository


class SourceRepository(BaseRepository[Source]):
    """Repository for external source entities."""

    model = Source

    async def get_by_name(self, name: str) -> Source | None:
        """Get a source by name."""
        result = await self.session.execute(select(Source).where(Source.name == name))
        return result.scalar_one_or_none()

    async def get_by_type(self, source_type: SourceType | str) -> Source | None:
        """Get the first active source of a given type."""
        if isinstance(source_type, str):
            source_type = SourceType(source_type)
        result = await self.session.execute(
            select(Source)
            .where(Source.source_type == source_type, Source.is_active.is_(True))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[Source]:
        """List all active sources."""
        result = await self.session.execute(
            select(Source).where(Source.is_active.is_(True)).order_by(Source.name)
        )
        return list(result.scalars().all())

    async def ensure_default(self, name: str, source_type: SourceType, **values: object) -> Source:
        """Get or create a source by name."""
        source = await self.get_by_name(name)
        if source is None:
            source = Source(name=name, source_type=source_type, **values)
            self.session.add(source)
            await self.session.flush()
        return source

    async def record_health(
        self,
        source_id,
        status: str,
        latency_ms: float | None = None,
        error_rate: float = 0.0,
    ) -> SourceHealth:
        """Record a health check result for a source."""
        from datetime import UTC, datetime

        health = SourceHealth(
            source_id=source_id,
            status=status,
            latency_ms=latency_ms,
            error_rate=error_rate,
            last_check_at=datetime.now(UTC),
        )
        self.session.add(health)
        await self.session.flush()
        return health
