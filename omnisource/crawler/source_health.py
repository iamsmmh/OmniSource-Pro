"""Bounded source probes with durable, privacy-safe health history."""

import asyncio
import time
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.config.logging import get_logger
from omnisource.connectors.base import ConnectorHealth, SourceConnector
from omnisource.connectors.registry import available_sources, create_connector
from omnisource.core.models.source import SourceType
from omnisource.core.repositories.source import SourceRepository

logger = get_logger(__name__)

_PUBLIC_FAILURE = "source_unavailable"


@dataclass(frozen=True)
class SourceProbe:
    """A single externally observed probe result before it is persisted."""

    source_type: str
    health: ConnectorHealth


class SourceHealthService:
    """Probe sources concurrently, then append results using one DB session.

    An ``AsyncSession`` must not be used by concurrent tasks. This service
    deliberately separates network probes from sequential persistence so one
    endpoint/job remains both quick and transaction-safe.
    """

    def __init__(self, session: AsyncSession, timeout_seconds: float = 15.0) -> None:
        self.session = session
        self.timeout_seconds = max(1.0, timeout_seconds)

    async def probe(self, source_type: str) -> SourceProbe:
        """Probe one connector with a total time budget and sanitized failures."""
        connector: SourceConnector | None = None
        started = time.perf_counter()
        try:
            connector = create_connector(source_type)
            await asyncio.wait_for(connector.initialize(), timeout=self.timeout_seconds)
            health = await asyncio.wait_for(connector.health_check(), timeout=self.timeout_seconds)
            latency_ms = health.latency_ms
            if latency_ms is None:
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
            return SourceProbe(
                source_type=source_type,
                health=ConnectorHealth(
                    source=source_type,
                    healthy=health.healthy,
                    latency_ms=latency_ms,
                    error_rate=health.error_rate,
                    last_check=health.last_check,
                    last_success=health.last_success,
                    last_error=None if health.healthy else _PUBLIC_FAILURE,
                ),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            # Provider errors are useful in protected logs but must not reach a
            # public health response or a long-lived database audit record.
            logger.warning(
                "Source health probe failed", exc_info=True, extra={"source": source_type}
            )
            return SourceProbe(
                source_type=source_type,
                health=ConnectorHealth(
                    source=source_type,
                    healthy=False,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    error_rate=0.0,
                    last_error=_PUBLIC_FAILURE,
                ),
            )
        finally:
            if connector is not None:
                with suppress(Exception):
                    await asyncio.wait_for(
                        connector.close(), timeout=min(5.0, self.timeout_seconds)
                    )

    async def probe_all(self, source_types: Iterable[str] | None = None) -> list[SourceProbe]:
        """Probe all registered (or explicitly selected) source types concurrently."""
        selected = list(source_types) if source_types is not None else available_sources()
        return list(await asyncio.gather(*(self.probe(source_type) for source_type in selected)))

    async def persist(self, probes: Iterable[SourceProbe]) -> list[ConnectorHealth]:
        """Upsert source configuration and append health records sequentially."""
        repository = SourceRepository(self.session)
        persisted: list[ConnectorHealth] = []
        for probe in probes:
            try:
                source_kind = SourceType(probe.source_type)
            except ValueError:
                logger.warning(
                    "Skipping unknown source type in health probe: %s", probe.source_type
                )
                continue
            connector = create_connector(probe.source_type)
            source = await repository.ensure_default(
                name=connector.source_name or probe.source_type,
                source_type=source_kind,
                base_url=connector.base_url or f"https://{probe.source_type}.invalid",
                api_url=connector.api_url or None,
                is_active=True,
            )
            await repository.record_connector_health(source.id, probe.health)
            persisted.append(probe.health)
        await self.session.commit()
        return persisted

    async def check_all(self, source_types: Iterable[str] | None = None) -> list[ConnectorHealth]:
        """Probe selected sources and persist their current operational state."""
        return await self.persist(await self.probe_all(source_types))


__all__ = ["SourceHealthService", "SourceProbe"]
