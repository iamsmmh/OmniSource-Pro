"""Tests for API security, rate limiting, webhooks, admin, and metrics."""

import hashlib
import hmac
import json
from unittest.mock import patch

import pytest

os_environ = {
    "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    "MEILISEARCH_URL": "",
}


from omnisource.api.rate_limit import InMemoryRateLimiter, RedisRateLimiter
from omnisource.api.routes.webhooks import _verify_github_signature
from omnisource.api.security import APIKeyAuth

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def webhook_secret():
    """Configure webhook secrets on the cached settings for the test."""
    from omnisource.config.settings import get_settings

    sources = get_settings().sources
    sources.WEBHOOK_SECRET_GITHUB = "test-secret"
    sources.WEBHOOK_SECRET_GITLAB = "test-secret"
    sources.WEBHOOK_SECRET_GITEA = "test-secret"
    yield "test-secret"
    sources.WEBHOOK_SECRET_GITHUB = None
    sources.WEBHOOK_SECRET_GITLAB = None
    sources.WEBHOOK_SECRET_GITEA = None


class TestAPIKeyAuth:
    def test_verify_constant_time(self):
        auth = APIKeyAuth(keys=["secret-key-1", "secret-key-2"])
        assert auth.verify("secret-key-1") is True
        assert auth.verify("wrong") is False
        assert auth.verify(None) is False

    def test_disabled_without_keys(self):
        auth = APIKeyAuth(keys=[])
        assert auth.enabled is False
        assert auth.verify("anything") is False


class TestAdminEndpoints:
    async def test_admin_requires_key(self, client_factory):
        client = client_factory()
        response = await client.get("/api/v1/admin/overview")
        assert response.status_code == 401

    async def test_admin_rejects_wrong_key(self, client_factory):
        with patch("omnisource.api.security.APIKeyAuth.verify", return_value=False):
            client = client_factory(headers={"X-API-Key": "nope"})
            response = await client.get("/api/v1/admin/overview")
        assert response.status_code == 401

    async def test_admin_accepts_valid_key(self, client_factory):
        with patch("omnisource.api.security.APIKeyAuth.verify", return_value=True):
            client = client_factory(headers={"X-API-Key": "good"})
            response = await client.get("/api/v1/admin/overview")
        assert response.status_code == 200
        body = response.json()
        assert "applications" in body and "repositories" in body

    async def test_dashboard_html(self, client_factory):
        client = client_factory()
        response = await client.get("/admin")
        assert response.status_code == 200
        assert "OmniSource Admin" in response.text


class TestRateLimiting:
    async def test_in_memory_limiter_windows(self):
        limiter = InMemoryRateLimiter()
        # limit 2/window
        ok1, rem1, _ = await limiter.check("k", limit=2, window_seconds=60)
        ok2, rem2, _ = await limiter.check("k", limit=2, window_seconds=60)
        ok3, rem3, reset = await limiter.check("k", limit=2, window_seconds=60)
        assert ok1 and ok2
        assert not ok3
        assert rem3 == 0
        assert reset >= 1
        # other keys unaffected
        ok_other, _, _ = await limiter.check("other", limit=2, window_seconds=60)
        assert ok_other

    async def test_redis_limiter_falls_back_offline(self):
        limiter = RedisRateLimiter("redis://localhost:9999/0")
        allowed, _, _ = await limiter.check("k", limit=1, window_seconds=60)
        assert allowed is True
        allowed2, _, _ = await limiter.check("k", limit=1, window_seconds=60)
        assert allowed2 is False  # in-memory fallback enforced the limit

    async def test_429_when_limit_exceeded(self, client_factory):
        from omnisource.api.main import get_settings

        settings = get_settings()
        original = settings.api.API_RATE_LIMIT
        settings.api.API_RATE_LIMIT = 1
        import time as _time

        headers = {"X-API-Key": f"limit-test-{_time.monotonic_ns()}"}
        try:
            client = client_factory()
            r1 = await client.get("/api/v1/stats", headers=headers)
            r2 = await client.get("/api/v1/stats", headers=headers)
            assert r1.status_code == 200
            assert r2.status_code == 429
            assert "Retry-After" in r2.headers
        finally:
            settings.api.API_RATE_LIMIT = original


class TestWebhooks:
    def test_github_signature_verification(self):
        secret = "whsec"
        body = b'{"action": "published"}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert _verify_github_signature(body, sig, secret) is True
        assert _verify_github_signature(body, "sha256=deadbeef", secret) is False
        assert _verify_github_signature(body, None, secret) is False

    async def test_github_webhook_requires_configured_secret(self, client_factory):
        from omnisource.config.settings import get_settings

        sources = get_settings().sources
        saved = sources.WEBHOOK_SECRET_GITHUB
        sources.WEBHOOK_SECRET_GITHUB = None
        try:
            client = client_factory()
            response = await client.post(
                "/api/v1/webhooks/github",
                json={"repository": {"full_name": "a/b"}},
                headers={"X-Hub-Signature-256": "sha256=x", "X-GitHub-Event": "push"},
            )
            assert response.status_code == 503
        finally:
            sources.WEBHOOK_SECRET_GITHUB = saved

    async def test_github_webhook_invalid_signature(self, client_factory, webhook_secret):
        client = client_factory()
        response = await client.post(
            "/api/v1/webhooks/github",
            content=json.dumps({"repository": {"full_name": "a/b"}}).encode(),
            headers={
                "X-Hub-Signature-256": "sha256=badbadbad",
                "X-GitHub-Event": "push",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 401

    async def test_github_webhook_valid_push_enqueues(self, client_factory, webhook_secret):
        secret = webhook_secret
        payload = {"repository": {"full_name": "localsend/localsend"}}
        body = json.dumps(payload).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        enqueued: list[dict] = []

        async def fake_enqueue(job):
            enqueued.append(job)
            return "job-123"

        with patch("omnisource.api.routes.webhooks.enqueue_job", side_effect=fake_enqueue):
            client = client_factory()
            response = await client.post(
                "/api/v1/webhooks/github",
                content=body,
                headers={
                    "X-Hub-Signature-256": sig,
                    "X-GitHub-Event": "push",
                    "Content-Type": "application/json",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["repository"] == "localsend/localsend"
        assert enqueued and enqueued[0]["type"] == "sync_releases"

    async def test_github_webhook_ignores_other_events(self, client_factory, webhook_secret):
        secret = webhook_secret
        payload = {"repository": {"full_name": "a/b"}}
        body = json.dumps(payload).encode()
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        client = client_factory()
        response = await client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "fork",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"


class TestMetrics:
    async def test_metrics_endpoint_exposes_prometheus_format(self, client_factory):
        client = client_factory()
        # generate some traffic first
        await client.get("/health/live")
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert "omnisource_http_requests_total" in response.text

    async def test_job_recording(self):
        from omnisource.api.metrics import record_job

        record_job("full_sync", "completed", 1.5)  # must not raise
