"""Smoke tests for the FastAPI surface using an in-process ASGI transport."""

from unittest.mock import patch

import httpx

from omnisource.api.main import app


async def _client():
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_health_endpoint(seeded_application):
    async with await _client() as client:
        response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"healthy", "degraded"}
    assert "database" in body["components"]


async def test_list_apps_endpoint(seeded_application):
    async with await _client() as client:
        response = await client.get("/api/v1/apps")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["items"][0]["id"] == "localsend"
    assert body["pagination"]["total"] == 1
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["has_next"] is False


async def test_get_app_by_slug(seeded_application):
    async with await _client() as client:
        response = await client.get("/api/v1/apps/localsend")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["name"] == "localsend"
    assert body["data"]["license"] == "Apache-2.0"
    assert "linux" in body["data"]["platforms"]


async def test_trending_and_latest(seeded_application):
    async with await _client() as client:
        trending = await client.get("/api/v1/trending")
        latest = await client.get("/api/v1/latest")
    assert trending.status_code == 200
    assert trending.json()["success"] is True
    assert len(trending.json()["data"]["items"]) == 1
    assert latest.status_code == 200
    assert latest.json()["success"] is True
    assert len(latest.json()["data"]["items"]) == 1


async def test_stats_endpoint(seeded_application):
    async with await _client() as client:
        response = await client.get("/api/v1/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["applications"] == 1
    assert body["data"]["repositories"] == 1


async def test_search_endpoint(seeded_application):
    async with await _client() as client:
        response = await client.get("/api/v1/search", params={"q": "local"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["pagination"]["total"] == 1
    assert body["data"]["items"][0]["id"] == "localsend"
    assert body["meta"]["backend"] == "database"


async def test_collections_endpoints(seeded_application):
    headers = {"X-OmniStore-Subject": "test-user"}
    async with await _client() as client:
        with patch("omnisource.api.security.APIKeyAuth.verify", return_value=True):
            created = await client.post(
                "/api/v1/collections",
                json={"name": "My apps", "is_public": True},
                headers=headers,
            )
            assert created.status_code == 201
            collection = created.json()["data"]
            assert created.json()["success"] is True

            added = await client.post(
                f"/api/v1/collections/{collection['id']}/apps",
                json={"app_id": "localsend"},
                headers=headers,
            )
            assert added.status_code == 200
            assert len(added.json()["data"]["items"]) == 1

            mine = await client.get("/api/v1/collections/mine", headers=headers)
            assert mine.status_code == 200
            assert mine.json()["success"] is True
            assert mine.json()["pagination"]["total"] == 1

        public = await client.get("/api/v1/collections")
        assert public.status_code == 200
        public_body = public.json()
        assert public_body["success"] is True
        assert public_body["pagination"]["total"] == 1
        assert public_body["data"]["items"][0]["id"] == collection["id"]


async def test_linux_feed_endpoint(seeded_application):
    async with await _client() as client:
        response = await client.get("/feeds/v1/linux.json")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_app_not_found(seeded_application):
    async with await _client() as client:
        response = await client.get("/api/v1/apps/does-not-exist")
    assert response.status_code == 404
