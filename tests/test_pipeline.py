"""End-to-end tests for the ingestion, sync, and automation pipeline."""

from unittest.mock import patch

from sqlalchemy import func, select, update

from omnisource.automation.jobs.index import run_indexing
from omnisource.automation.jobs.validate import run_validation
from omnisource.core.models.application import (
    Application,
    application_architectures,
    application_platforms,
)
from omnisource.core.models.asset import Asset, AssetStatus
from omnisource.core.models.repository import Repository, RepositoryMetadata
from omnisource.core.models.scores import TrustScore
from omnisource.core.models.source import Source, SourceType
from omnisource.crawler.discovery import DiscoveryService
from omnisource.crawler.sync import RepositorySyncService
from omnisource.feeds.generator import FeedGenerator


async def test_discovery_ingests_repository(session, mock_connector):
    with patch(
        "omnisource.crawler.discovery.create_connector",
        return_value=mock_connector,
    ):
        result = await DiscoveryService(session).discover(source_type="github")

    assert result["discovered"] == 1
    assert result["ingested"] == 1

    repositories = (await session.execute(select(Repository))).scalars().all()
    assert len(repositories) == 1


async def test_sync_repository_builds_application_graph(session, mock_connector):
    source = Source(
        name="GitHub", source_type=SourceType.GITHUB, base_url="https://github.com", is_active=True
    )
    session.add(source)
    await session.flush()

    repository = Repository(
        source_id=source.id,
        external_id="123",
        full_name="localsend/localsend",
        name="localsend",
        html_url="https://github.com/localsend/localsend",
        stars=5000,
        forks=300,
    )
    session.add(repository)
    await session.flush()
    session.add(
        RepositoryMetadata(
            repository_id=repository.id,
            topics=["file-sharing"],
            license_spdx="Apache-2.0",
            readme="# LocalSend",
        )
    )
    await session.commit()

    result = await RepositorySyncService(session).sync_repository(mock_connector, repository)
    await session.commit()

    assert result["releases"] == 1
    assert result["assets"] == 1

    app = (
        await session.execute(
            select(Application).where(Application.app_id == "localsend/localsend")
        )
    ).scalar_one()

    assert app.developer_id is not None
    assert app.license_id is not None
    assert [p.platform_type for p in app.platforms] == ["linux"]
    assert [a.architecture_type for a in app.architectures] == ["x86_64"]

    platform_rows = await session.scalar(select(func.count()).select_from(application_platforms))
    arch_rows = await session.scalar(select(func.count()).select_from(application_architectures))
    assert platform_rows == 1
    assert arch_rows == 1

    scores = (await session.execute(select(TrustScore))).scalars().all()
    assert len(scores) == 1


async def test_sync_source_commits_batch(session, mock_connector):
    source = Source(
        name="GitHub", source_type=SourceType.GITHUB, base_url="https://github.com", is_active=True
    )
    session.add(source)
    await session.flush()

    repository = Repository(
        source_id=source.id,
        external_id="123",
        full_name="localsend/localsend",
        name="localsend",
        html_url="https://github.com/localsend/localsend",
        stars=5000,
        forks=300,
    )
    session.add(repository)
    await session.flush()
    session.add(
        RepositoryMetadata(
            repository_id=repository.id,
            topics=["file-sharing"],
            license_spdx="Apache-2.0",
        )
    )
    await session.commit()

    with patch(
        "omnisource.crawler.sync.create_connector",
        return_value=mock_connector,
    ):
        result = await RepositorySyncService(session).sync_source(source_type="github")

    assert result["repositories"] == 1
    assert result["releases"] == 1
    assert result["assets"] == 1


async def test_validation_job_repairs_pending_assets(seeded_session, mock_connector):
    session, repository, _source = seeded_session

    await RepositorySyncService(session).sync_repository(mock_connector, repository)
    await session.commit()

    await session.execute(update(Asset).values(status=AssetStatus.PENDING))
    await session.commit()

    result = await run_validation(session)
    assert result["validated"] == 1

    asset = (await session.execute(select(Asset))).scalar_one()
    assert asset.status == AssetStatus.VALID


async def test_indexing_job_uses_null_indexer(seeded_application):
    result = await run_indexing(seeded_application)
    assert result["indexed"] == 1


async def test_feed_generation(seeded_application):
    generator = FeedGenerator(seeded_application)
    result = await generator.generate("linux")
    assert result["total"] == 1

    universal = await generator.generate("all")
    assert universal["total"] == 1
