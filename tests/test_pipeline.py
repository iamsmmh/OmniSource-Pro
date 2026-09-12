"""End-to-end tests for the ingestion, sync, and automation pipeline."""

from unittest.mock import patch

from sqlalchemy import func, select, update

from omnisource.automation.jobs.index import run_indexing
from omnisource.automation.jobs.validate import run_validation
from omnisource.connectors.base import ConnectorHealth, PageInfo, SourceConnector
from omnisource.core.models.application import (
    Application,
    OpenSourceStatus,
    application_architectures,
    application_platforms,
)
from omnisource.core.models.asset import Asset, AssetStatus
from omnisource.core.models.release import Release
from omnisource.core.models.repository import Repository, RepositoryMetadata
from omnisource.core.models.scores import TrustScore
from omnisource.core.models.source import Source, SourceType
from omnisource.core.schemas.repository import RepositorySchema
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


class FmhyMockConnector(SourceConnector):
    """A minimal FMHY-like connector: a directory entry with no releases."""

    source_name = "fmhy"
    source_type = "fmhy"

    async def initialize(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def discover(self, query=None, cursor=None, limit=100, **kwargs):
        return [], PageInfo()

    async def get_repository(self, repository_id, **kwargs):
        return RepositorySchema(
            external_id="cypwn",
            full_name="fmhy/cypwn",
            name="CyPwn",
            description="Tweaked App Library",
            homepage="https://ipa.cypwn.xyz/",
            html_url="https://ipa.cypwn.xyz/",
        )

    async def get_releases(self, repository, **kwargs):
        return []

    async def get_assets(self, release, **kwargs):
        return []

    async def get_metadata(self, repository, **kwargs):
        return {"source": "fmhy", "homepage": repository.homepage, "topics": ["ios", "ios-ipas"]}

    async def health_check(self):
        return ConnectorHealth(source="fmhy", healthy=True)


async def test_fmhy_sync_creates_ios_app_without_releases(session):
    """FMHY directory entries become iOS apps, UNKNOWN open-source, no releases."""
    source = Source(
        name="FMHY",
        source_type=SourceType.FMHY,
        base_url="https://fmhy.net",
        is_active=True,
    )
    session.add(source)
    await session.flush()

    repository = Repository(
        source_id=source.id,
        external_id="cypwn",
        full_name="fmhy/cypwn",
        name="CyPwn",
        description="Tweaked App Library",
        homepage="https://ipa.cypwn.xyz/",
        html_url="https://ipa.cypwn.xyz/",
    )
    session.add(repository)
    await session.flush()
    await session.commit()

    connector = FmhyMockConnector()
    await connector.initialize()
    try:
        result = await RepositorySyncService(session).sync_repository(connector, repository)
    finally:
        await connector.close()
    await session.commit()

    assert result["releases"] == 0
    assert result["assets"] == 0

    app = (
        await session.execute(select(Application).where(Application.app_id == "fmhy/cypwn"))
    ).scalar_one()

    # Directory listings are not auditable code: UNKNOWN, not assumed open-source.
    assert app.open_source_status == OpenSourceStatus.UNKNOWN
    # The iOS iPAs section tags every entry with the iOS platform.
    assert [p.platform_type for p in app.platforms] == ["ios"]
    assert app.homepage == "https://ipa.cypwn.xyz/"

    release_count = await session.scalar(select(func.count()).select_from(Release))
    asset_count = await session.scalar(select(func.count()).select_from(Asset))
    assert release_count == 0
    assert asset_count == 0


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


async def test_delta_sync_skips_unchanged(session, mock_connector):
    """Repos whose pushed_at is unchanged and freshly synced are skipped."""
    from datetime import UTC, datetime, timedelta

    source = Source(
        name="GitHub", source_type=SourceType.GITHUB, base_url="https://github.com", is_active=True
    )
    session.add(source)
    await session.flush()

    now = datetime.now(UTC)
    repository = Repository(
        source_id=source.id,
        external_id="123",
        full_name="localsend/localsend",
        name="localsend",
        html_url="https://github.com/localsend/localsend",
        pushed_at=now,
        last_synced_pushed_at=now,
        synced_at=now - timedelta(hours=1),
    )
    session.add(repository)
    await session.commit()

    with patch("omnisource.crawler.sync.create_connector", return_value=mock_connector):
        service = RepositorySyncService(session)
        result = await service.sync_source(source_type="github")
    await session.commit()

    assert result["skipped_unchanged"] == 1
    assert result["releases"] == 0


async def test_delta_sync_resyncs_when_pushed_at_advances(session, mock_connector):
    """A newer upstream pushed_at forces a full release sync."""
    from datetime import UTC, datetime, timedelta

    source = Source(
        name="GitHub", source_type=SourceType.GITHUB, base_url="https://github.com", is_active=True
    )
    session.add(source)
    await session.flush()

    stale = datetime.now(UTC) - timedelta(days=30)
    repository = Repository(
        source_id=source.id,
        external_id="123",
        full_name="localsend/localsend",
        name="localsend",
        html_url="https://github.com/localsend/localsend",
        pushed_at=stale,
        last_synced_pushed_at=stale,
        synced_at=stale,
    )
    session.add(repository)
    await session.commit()

    with patch("omnisource.crawler.sync.create_connector", return_value=mock_connector):
        service = RepositorySyncService(session)
        result = await service.sync_source(source_type="github")
    await session.commit()

    assert result["skipped_unchanged"] == 0
    assert result["releases"] == 1


async def test_delta_sync_resyncs_stale_repos(session, mock_connector):
    """max_sync_age_hours forces a refresh even when pushed_at is unchanged."""
    from datetime import UTC, datetime, timedelta

    from omnisource.crawler.policies import ProcessingPolicies

    source = Source(
        name="GitHub", source_type=SourceType.GITHUB, base_url="https://github.com", is_active=True
    )
    session.add(source)
    await session.flush()

    month_ago = datetime.now(UTC) - timedelta(days=30)
    repository = Repository(
        source_id=source.id,
        external_id="123",
        full_name="localsend/localsend",
        name="localsend",
        html_url="https://github.com/localsend/localsend",
        pushed_at=month_ago,
        last_synced_pushed_at=month_ago,
        synced_at=month_ago,  # stale beyond max_sync_age_hours
    )
    session.add(repository)
    await session.commit()

    with patch("omnisource.crawler.sync.create_connector", return_value=mock_connector):
        service = RepositorySyncService(session, policies=ProcessingPolicies(max_sync_age_hours=1))
        result = await service.sync_source(source_type="github")
    await session.commit()

    assert result["skipped_unchanged"] == 0
    assert result["releases"] == 1


async def test_sync_flags_breaking_changes(session, mock_connector):
    """The sync pipeline computes breaking-change flags from versions+notes."""
    from datetime import UTC, datetime

    from omnisource.core.models.release import Release

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
    )
    session.add(repository)
    await session.commit()

    from omnisource.core.schemas.asset import AssetSchema, AssetSourceSchema, AssetStatusSchema
    from omnisource.core.schemas.release import ReleaseSchema, ReleaseStatusSchema

    def _asset(version: str, asset_num: str) -> AssetSchema:
        return AssetSchema(
            asset_id=f"gh-{asset_num}",
            filename=f"localsend-{version}.AppImage",
            download_url=f"https://example.com/{version}.AppImage",
            file_type="appimage",
            detected_platform="linux",
            package_type="appimage",
            version=version,
            source=AssetSourceSchema.GITHUB_RELEASE,
            status=AssetStatusSchema.PENDING,
        )

    async def fake_assets(release, **kwargs):
        return [_asset(release.version, "1" if release.version == "1.0.0" else "2")]

    with (
        patch.object(
            mock_connector,
            "get_releases",
            return_value=[
                ReleaseSchema(
                    external_id="r1",
                    version="1.0.0",
                    body="Initial release",
                    status=ReleaseStatusSchema.RELEASED,
                    published_at=datetime.now(UTC),
                    repository_id=repository.id,
                ),
                ReleaseSchema(
                    external_id="r2",
                    version="2.0.0",
                    body="BREAKING CHANGE: config file format changed",
                    status=ReleaseStatusSchema.RELEASED,
                    published_at=datetime.now(UTC),
                    repository_id=repository.id,
                ),
            ],
        ),
        patch.object(mock_connector, "get_assets", side_effect=fake_assets),
    ):
        await RepositorySyncService(session).sync_repository(mock_connector, repository)
    await session.commit()

    releases = {r.version: r for r in (await session.execute(select(Release))).scalars().all()}
    assert releases["1.0.0"].has_breaking_changes is False
    assert releases["2.0.0"].has_breaking_changes is True
    assert "major_version_bump" in releases["2.0.0"].breaking_signals
