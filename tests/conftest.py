"""Shared fixtures for the OmniSource test suite.

Tests run against an in-memory SQLite database so no external services are
required. The ``DATABASE_URL`` must be set before settings are loaded, which
is why it is assigned at module import time.
"""

import os
from datetime import datetime, UTC

import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("MEILISEARCH_URL", "")  # disable search indexing in tests

from omnisource.config.settings import reload_settings  # noqa: E402

reload_settings()

from omnisource.core.database.base import close_db, get_async_engine  # noqa: E402
from omnisource.core.database.session import create_session  # noqa: E402
from omnisource.core.models import Base  # noqa: E402
from omnisource.core.models.application import Application, OpenSourceStatus  # noqa: E402
from omnisource.core.models.category import Category  # noqa: E402
from omnisource.core.models.developer import Developer  # noqa: E402
from omnisource.core.models.license import License  # noqa: E402
from omnisource.core.models.platform import Platform  # noqa: E402
from omnisource.core.models.release import Release, ReleaseAsset, ReleaseStatus  # noqa: E402
from omnisource.core.models.asset import (  # noqa: E402
    Asset,
    AssetSource,
    AssetStatus,
)
from omnisource.core.models.repository import (  # noqa: E402
    Repository,
    RepositoryMetadata,
)
from omnisource.core.models.scores import (  # noqa: E402
    PopularityScore,
    QualityScore,
    TrustScore,
)
from omnisource.core.models.source import Source, SourceType  # noqa: E402
from omnisource.core.schemas.asset import (  # noqa: E402
    AssetSchema,
    AssetSourceSchema,
    AssetStatusSchema,
)
from omnisource.core.schemas.release import ReleaseSchema, ReleaseStatusSchema  # noqa: E402
from omnisource.core.schemas.repository import RepositorySchema  # noqa: E402
from omnisource.connectors.base import (  # noqa: E402
    ConnectorHealth,
    PageInfo,
    SourceConnector,
)


class MockConnector(SourceConnector):
    """A fake GitHub connector that returns a single well-known repository."""

    source_name = "github"

    async def initialize(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def discover(self, query=None, cursor=None, limit=100, **kwargs):
        return [
            RepositorySchema(
                external_id="123",
                full_name="localsend/localsend",
                name="localsend",
                description="Share files to nearby devices",
                html_url="https://github.com/localsend/localsend",
                stars=5000,
                forks=300,
            )
        ], PageInfo(next_cursor="cursor-2", has_next=True)

    async def get_repository(self, repository_id, **kwargs):
        return RepositorySchema(
            external_id="123",
            full_name="localsend/localsend",
            name="localsend",
            html_url="https://github.com/localsend/localsend",
        )

    async def get_releases(self, repository, **kwargs):
        return [
            ReleaseSchema(
                external_id="r1",
                version="v1.0.0",
                tag="v1.0.0",
                status=ReleaseStatusSchema.RELEASED,
                published_at=datetime.now(UTC),
                repository_id=repository.id,
            )
        ]

    async def get_assets(self, release, **kwargs):
        return [
            AssetSchema(
                asset_id="gh-1",
                filename="localsend-linux.AppImage",
                display_name="AppImage",
                download_url="https://example.com/localsend.AppImage",
                size_bytes=1024,
                mime_type="application/octet-stream",
                file_type="appimage",
                detected_platform="linux",
                detected_architecture="x86_64",
                package_type="appimage",
                version=release.version,
                source=AssetSourceSchema.GITHUB_RELEASE,
                status=AssetStatusSchema.PENDING,
                release_id=release.id,
            )
        ]

    async def get_metadata(self, repository, **kwargs):
        return {"topics": ["file-sharing", "lan"], "license_spdx": "Apache-2.0"}

    async def health_check(self):
        return ConnectorHealth(source="github", healthy=True)


@pytest_asyncio.fixture
async def mock_connector():
    return MockConnector()


@pytest_asyncio.fixture(autouse=True)
async def database():
    """Create a fresh schema before each test and dispose it afterwards."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await close_db()


@pytest_asyncio.fixture
async def session():
    async with create_session() as s:
        yield s


@pytest_asyncio.fixture
async def seeded_session(session):
    """A session seeded with a source, repository, and its metadata."""
    source = Source(
        name="GitHub",
        source_type=SourceType.GITHUB,
        base_url="https://github.com",
        is_active=True,
    )
    session.add(source)
    await session.flush()

    repository = Repository(
        source_id=source.id,
        external_id="123",
        full_name="localsend/localsend",
        name="localsend",
        description="Share files to nearby devices",
        html_url="https://github.com/localsend/localsend",
        stars=5000,
        forks=300,
    )
    session.add(repository)
    await session.flush()

    metadata = RepositoryMetadata(
        repository_id=repository.id,
        topics=["file-sharing", "lan"],
        license_spdx="Apache-2.0",
        readme="# LocalSend",
    )
    session.add(metadata)
    await session.commit()

    return session, repository, source


@pytest_asyncio.fixture
async def seeded_application(session):
    """A fully populated application graph for repository/API tests."""
    source = Source(
        name="GitHub",
        source_type=SourceType.GITHUB,
        base_url="https://github.com",
        is_active=True,
    )
    session.add(source)
    await session.flush()

    repository = Repository(
        source_id=source.id,
        external_id="123",
        full_name="localsend/localsend",
        name="localsend",
        description="Share files",
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

    platform = Platform(
        platform_type="linux", name="linux", display_name="Linux", is_active=True
    )
    category = Category(
        category_type="utilities", name="Utilities", slug="utilities"
    )
    license_obj = License(
        license_id="apache-2.0",
        spdx_id="Apache-2.0",
        name="Apache License 2.0",
        short_name="Apache-2.0",
        is_osi_approved=True,
    )
    developer = Developer(
        developer_id="localsend", slug="localsend", name="LocalSend Contributors"
    )
    app = Application(
        app_id="localsend/localsend",
        slug="localsend",
        name="localsend",
        long_description="Share files",
        open_source_status=OpenSourceStatus.OPEN_SOURCE,
        is_active=True,
        developer=developer,
        license=license_obj,
    )
    session.add_all([developer, license_obj])
    app.repositories.append(repository)
    app.platforms.append(platform)
    app.categories.append(category)
    session.add_all([platform, category, app])
    await session.flush()

    release = Release(
        application_id=app.id,
        repository_id=repository.id,
        external_id="r1",
        version="1.0.0",
        status=ReleaseStatus.RELEASED,
    )
    session.add(release)
    await session.flush()

    asset = Asset(
        asset_id="a1",
        filename="localsend.AppImage",
        download_url="https://example.com/localsend.AppImage",
        detected_platform="linux",
        detected_architecture="x86_64",
        package_type="appimage",
        status=AssetStatus.VALID,
        source=AssetSource.GITHUB_RELEASE,
        version="1.0.0",
    )
    session.add(asset)
    await session.flush()

    session.add(ReleaseAsset(release_id=release.id, asset_id=asset.id))
    await session.flush()

    session.add_all(
        [
            TrustScore(application_id=app.id, score=0.9, normalized_score=90.0, factors={"a": 0.9}),
            QualityScore(application_id=app.id, score=0.8, normalized_score=80.0, factors={"b": 0.8}),
            PopularityScore(application_id=app.id, score=0.7, normalized_score=70.0, factors={"c": 0.7}),
        ]
    )
    await session.commit()
    return session
