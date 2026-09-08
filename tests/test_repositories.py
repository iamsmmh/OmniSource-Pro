"""Tests for repository querying, filtering, and OmniStore mapping."""

from omnisource.core.repositories.application import ApplicationRepository


async def test_get_app_by_id_or_slug(seeded_application):
    repo = ApplicationRepository(seeded_application)
    app = await repo.get_app_by_id_or_slug("localsend/localsend")
    assert app is not None
    assert app.name == "localsend"
    assert app.platforms == ["linux"]
    assert app.categories == ["utilities"]


async def test_get_apps_paginated_with_platform_filter(seeded_application):
    repo = ApplicationRepository(seeded_application)

    page = await repo.get_apps_paginated(platform="linux", page=1, per_page=30)
    assert page.total == 1
    assert page.items[0].id == "localsend"

    empty = await repo.get_apps_paginated(platform="windows", page=1, per_page=30)
    assert empty.total == 0


async def test_get_apps_paginated_min_trust_filter(seeded_application):
    repo = ApplicationRepository(seeded_application)

    page = await repo.get_apps_paginated(min_trust=10, page=1, per_page=30)
    assert page.total == 1

    page = await repo.get_apps_paginated(min_trust=95, page=1, per_page=30)
    assert page.total == 0


async def test_trending_and_latest(seeded_application):
    repo = ApplicationRepository(seeded_application)
    assert len(await repo.get_trending()) == 1
    assert len(await repo.get_latest()) == 1


async def test_omnistore_mapping_status(seeded_application):
    repo = ApplicationRepository(seeded_application)
    app = await repo.get_app_by_id_or_slug("localsend/localsend")

    assert app is not None
    assert app.scores is not None
    assert app.scores.trust == 90

    # Asset status must be mapped to OmniStore's uppercase enum values.
    asset = app.latest_release.assets[0]
    assert asset.status.value == "VALID"
    assert asset.platform.value == "linux"
