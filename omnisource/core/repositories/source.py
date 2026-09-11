"""Repository operations for configured external software sources."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from omnisource.connectors.base import ConnectorHealth
from omnisource.core.models.source import Source, SourceHealth, SourceHealthStatus, SourceType
from omnisource.core.repositories.base import BaseRepository


class SourceRepository(BaseRepository[Source]):
    """Persistence access for sources and their append-only health history."""

    model = Source

    async def get_by_name(self, name: str) -> Source | None:
        """Get a source by its unique human-readable name."""
        result = await self.session.execute(select(Source).where(Source.name == name))
        return result.scalar_one_or_none()

    async def get_by_type(self, source_type: SourceType | str) -> Source | None:
        """Get the first active configured source of a given source type."""
        if isinstance(source_type, str):
            source_type = SourceType(source_type)
        result = await self.session.execute(
            select(Source)
            .where(Source.source_type == source_type, Source.is_active.is_(True))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[Source]:
        """List active sources in a stable order."""
        result = await self.session.execute(
            select(Source).where(Source.is_active.is_(True)).order_by(Source.name)
        )
        return list(result.scalars().all())

    async def ensure_default(self, name: str, source_type: SourceType, **values: object) -> Source:
        """Get or create the configured record for a source type.

        ``name`` is retained as a fallback for legacy data. New callers should
        provide the connector's canonical source name and URLs.
        """
        source = await self.get_by_type(source_type)
        if source is None:
            source = await self.get_by_name(name)
        if source is None:
            source = Source(name=name, source_type=source_type, **values)
            self.session.add(source)
            await self.session.flush()
        return source

    async def latest_health(self, source_id: UUID) -> SourceHealth | None:
        """Return the most recent persisted probe result for one source."""
        result = await self.session.execute(
            select(SourceHealth)
            .where(SourceHealth.source_id == source_id)
            .order_by(SourceHealth.last_check_at.desc(), SourceHealth.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def record_connector_health(
        self,
        source_id: UUID,
        health: ConnectorHealth,
    ) -> SourceHealth:
        """Append a sanitized connector probe result to the source health history.

        Health records deliberately persist availability measurements, not raw
        upstream exception messages. Those messages can contain request paths,
        provider payloads, or accidentally configured credentials and belong in
        access-controlled application logs instead.
        """
        previous = await self.latest_health(source_id)
        now = datetime.now(UTC)
        status = self._status_for(health)
        healthy = status == SourceHealthStatus.HEALTHY
        health_record = SourceHealth(
            source_id=source_id,
            status=status,
            latency_ms=health.latency_ms,
            error_rate=max(0.0, min(1.0, float(health.error_rate))),
            last_check_at=now,
            last_success_at=now if healthy else (previous.last_success_at if previous else None),
            last_failure_at=None if healthy else now,
            consecutive_failures=0
            if healthy
            else (previous.consecutive_failures + 1 if previous else 1),
        )
        self.session.add(health_record)
        await self.session.flush()
        return health_record

    @staticmethod
    def _status_for(health: ConnectorHealth) -> SourceHealthStatus:
        """Map provider-neutral probe signals to a durable health state."""
        if health.healthy:
            return SourceHealthStatus.HEALTHY
        # A reported nonzero error rate means the provider responded but is not
        # fully usable. No response signal is treated as offline.
        return SourceHealthStatus.DEGRADED if health.error_rate > 0 else SourceHealthStatus.OFFLINE


__all__ = ["SourceRepository"]
