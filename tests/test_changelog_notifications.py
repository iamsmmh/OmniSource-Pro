"""Tests for changelog analysis and push notifications."""

import hashlib
import hmac
import json

import pytest

from omnisource.processing.changelog import (
    analyze_release,
    is_breaking_bump,
    notes_suggest_breaking,
    parse_version,
    summarize_range,
)

pytestmark = pytest.mark.asyncio


class TestParseVersion:
    def test_semver(self):
        v = parse_version("v1.2.3")
        assert v and (v.major, v.minor, v.patch) == (1, 2, 3)

    def test_semver_prerelease_and_build(self):
        v = parse_version("2.0.0-rc.1+build.5")
        assert v and v.prerelease == "rc.1" and v.build == "build.5"

    def test_non_semver(self):
        assert parse_version("2024.01") is None
        assert parse_version("latest") is None
        assert parse_version(None) is None

    def test_zero_major(self):
        v = parse_version("0.14.2")
        assert v and (v.major, v.minor) == (0, 14)


class TestBreakingBump:
    def test_major_bump_breaks(self):
        assert is_breaking_bump("1.4.2", "2.0.0") is True

    def test_minor_bump_does_not_break(self):
        assert is_breaking_bump("1.4.2", "1.5.0") is False

    def test_zero_x_minor_bump_breaks(self):
        assert is_breaking_bump("0.4.2", "0.5.0") is True

    def test_patch_bump_never_breaks(self):
        assert is_breaking_bump("0.4.2", "0.4.3") is False

    def test_unparseable_is_not_breaking(self):
        assert is_breaking_bump("latest", "2026.01") is False
        assert is_breaking_bump(None, "1.0.0") is False

    def test_downgrade_not_breaking(self):
        assert is_breaking_bump("2.0.0", "1.9.0") is False


class TestNotesSignals:
    def test_conventional_commit_breaking(self):
        assert notes_suggest_breaking("feat!: redesign the API surface") is True
        assert notes_suggest_breaking("fix: small bug\n\nBREAKING CHANGE: config format") is True

    def test_migration_phrases(self):
        assert notes_suggest_breaking("Migration required: run omnisource migrate") is True
        assert notes_suggest_breaking("This release is no longer compatible with v1") is True

    def test_normal_notes(self):
        assert notes_suggest_breaking("Bug fixes and performance improvements") is False
        assert notes_suggest_breaking(None) is False


class TestAnalyzeRelease:
    def test_combined_signals(self):
        result = analyze_release("1.2.9", "2.0.0", "BREAKING CHANGE: new config")
        assert result["has_breaking_changes"] is True
        assert set(result["signals"]) == {"major_version_bump", "breaking_notes"}
        assert result["parsed_version"]["major"] == 2

    def test_clean_release(self):
        result = analyze_release("1.2.9", "1.3.0", "Added a button")
        assert result["has_breaking_changes"] is False
        assert result["signals"] == []

    def test_no_versions_at_all(self):
        assert analyze_release(None, None, None)["has_breaking_changes"] is False


class TestSummarizeRange:
    def test_counts(self):
        summary = summarize_range(["1.0.0", "1.1.0", "2.0.0", "2.0.1"])
        assert summary == {
            "total": 4,
            "parsed_semver": 4,
            "breaking_transitions": 1,
        }


class TestNotifications:
    async def test_sign_payload(self):
        from omnisource.automation.notify import sign_payload

        body = b'{"event":"release.created"}'
        expected = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
        assert sign_payload("s3cret", body) == expected

    async def test_build_payload_shape(self):
        from omnisource.automation.notify import build_payload

        body = build_payload("release.created", {"version": "1.0.0"})
        data = json.loads(body)
        assert data["event"] == "release.created"
        assert data["data"] == {"version": "1.0.0"}
        assert "timestamp" in data

    async def test_dispatch_only_matching_subscriptions(self, session, respx_mock):
        from omnisource.automation.notify import dispatch_event
        from omnisource.core.models.notification import WebhookSubscription

        hits = respx_mock.post("https://consumer.example.com/hook").respond(json={"ok": True})
        missed = respx_mock.post("https://other.example.com/hook").respond(json={"ok": True})

        session.add(
            WebhookSubscription(
                url="https://consumer.example.com/hook",
                events=["release.created"],
                secret="s1",
            )
        )
        session.add(
            WebhookSubscription(
                url="https://other.example.com/hook",
                events=["feed.updated"],
                secret="s2",
            )
        )
        await session.commit()

        attempted = await dispatch_event(session, "release.created", {"version": "2.0.0"})
        assert attempted == 1
        assert hits.called
        assert not missed.called

    async def test_delivery_includes_signature_header(self, session, respx_mock):
        from omnisource.automation.notify import dispatch_event, sign_payload
        from omnisource.core.models.notification import WebhookSubscription

        route = respx_mock.post("https://consumer.example.com/hook").respond(json={"ok": True})
        session.add(
            WebhookSubscription(
                url="https://consumer.example.com/hook",
                events=["*"],
                secret="s3cret",
            )
        )
        await session.commit()

        await dispatch_event(session, "feed.updated", {"version": "v1"})
        request = route.calls.last.request
        signature = request.headers["X-OmniSource-Signature"]
        assert signature == sign_payload("s3cret", request.content)

    async def test_failures_disable_subscription(self, session, respx_mock):
        import httpx

        from omnisource.automation.notify import dispatch_event
        from omnisource.core.models.notification import WebhookSubscription

        respx_mock.post("https://flaky.example.com/hook").mock(
            side_effect=httpx.ConnectError("down")
        )
        subscription = WebhookSubscription(
            url="https://flaky.example.com/hook",
            events=["*"],
            secret="s",
        )
        subscription.failure_count = 19  # one failure from the cutoff
        session.add(subscription)
        await session.commit()

        await dispatch_event(session, "app.updated", {})
        assert subscription.is_active is False
        assert subscription.failure_count == 20

    async def test_event_validation(self):
        from omnisource.automation.notify import ensure_notification_events_valid

        assert ensure_notification_events_valid(["release.created", "*"]) == [
            "release.created",
            "*",
        ]
        assert ensure_notification_events_valid(["bogus"]) == []
