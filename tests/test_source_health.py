"""Tests for bounded, persisted external-source health telemetry."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from omnisource.connectors.base import ConnectorHealth, PageInfo, SourceConnector
from omnisource.core.models.source import Source, SourceHealth, SourceHealthStatus
from omnisource.crawler.source_health import SourceHealthService

pytestmark = pytest.mark.asyncio


class ProbeConnector(SourceConnector):
    """Minimal connector used to isolate probe orchestration from HTTP."""

    source_name = "GitHub"
    source_type = "github"
    base_url = "https://github.com"
    api_url = "https://api.github.com"
    healthy = True

    async def initialize(self) -> None:
        self._initialized = True

    async def close(self) -> None:
        self._initialized = False

    async def discover(self, **kwargs):
        return [], PageInfo()

    async def get_repository(self, repository_id: str, **kwargs):
        raise NotImplementedError

    async def get_releases(self, repository, **kwargs):
        raise NotImplementedError

    async def get_assets(self, release, **kwargs):
        raise NotImplementedError

    async def get_metadata(self, repository, **kwargs):
        return {}

    async def health_check(self) -> ConnectorHealth:
        if not self.healthy:
            return ConnectorHealth(
                source="github",
                healthy=False,
                error_rate=0.25,
                last_error="upstream response should never be persisted",
            )
        return ConnectorHealth(
            source="github",
            healthy=True,
            latency_ms=12.5,
            last_check=datetime.now(UTC),
        )


async def test_source_health_is_appended_without_storing_provider_errors(session, monkeypatch):
    from omnisource.crawler import source_health

    monkeypatch.setattr(source_health, "create_connector", lambda _: ProbeConnector())
    service = SourceHealthService(session, timeout_seconds=1)

    first = await service.check_all(["github"])
    assert first[0].healthy is True

    ProbeConnector.healthy = False
    try:
        second = await service.check_all(["github"])
    finally:
        ProbeConnector.healthy = True

    assert second[0].last_error == "source_unavailable"
    source = (await session.execute(select(Source))).scalar_one()
    records = (
        (
            await session.execute(
                select(SourceHealth)
                .where(SourceHealth.source_id == source.id)
                .order_by(SourceHealth.last_check_at)
            )
        )
        .scalars()
        .all()
    )
    assert [record.status for record in records] == [
        SourceHealthStatus.HEALTHY,
        SourceHealthStatus.DEGRADED,
    ]
    assert records[0].last_success_at is not None
    assert records[1].last_success_at == records[0].last_success_at
    assert records[1].consecutive_failures == 1


async def test_source_health_endpoint_returns_sanitized_connector_failure(
    client_factory, monkeypatch
):
    from omnisource.crawler import source_health

    ProbeConnector.healthy = False
    monkeypatch.setattr(source_health, "available_sources", lambda: ["github"])
    monkeypatch.setattr(source_health, "create_connector", lambda _: ProbeConnector())
    try:
        async with client_factory() as client:
            response = await client.get("/health/sources")
    finally:
        ProbeConnector.healthy = True

    assert response.status_code == 200
    response_body = response.json()
    assert response_body[0]["source"] == "github"
    assert response_body[0]["last_error"] == "source_unavailable"
    assert "upstream response" not in response.text
