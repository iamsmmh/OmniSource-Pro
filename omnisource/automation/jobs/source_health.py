"""Persisted health probes for every registered discovery source."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.crawler.source_health import SourceHealthService


async def run_source_health_check(
    session: AsyncSession,
    source_types: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, int]:
    """Probe source connectors concurrently and record their safe outcomes."""
    results = await SourceHealthService(session).check_all(source_types)
    return {
        "checked": len(results),
        "healthy": sum(1 for result in results if result.healthy),
        "unhealthy": sum(1 for result in results if not result.healthy),
    }


__all__ = ["run_source_health_check"]
