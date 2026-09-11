"""Configuration parsing and production-safety tests."""

import pytest
from pydantic import ValidationError

from omnisource.config.settings import APISettings, Settings


def test_api_settings_accept_comma_separated_keys_and_origins(monkeypatch):
    monkeypatch.setenv("API_KEYS", "first-key, second-key")
    monkeypatch.setenv("API_CORS_ORIGINS", "https://store.example, https://desktop.example")

    settings = APISettings()

    assert settings.API_KEYS == ["first-key", "second-key"]
    assert settings.API_CORS_ORIGINS == ["https://store.example", "https://desktop.example"]


def test_production_rejects_wildcard_cors_with_comma_delimited_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "a-32-character-secret-for-production")
    monkeypatch.setenv("MEILISEARCH_MASTER_KEY", "non-default-search-key")
    monkeypatch.setenv("FEED_SIGNING_PRIVATE_KEY", "configured-private-key")
    monkeypatch.setenv("FEED_ALLOW_EPHEMERAL_SIGNING", "false")
    monkeypatch.setenv("API_KEYS", "first-key,second-key")
    monkeypatch.setenv("API_CORS_ORIGINS", "https://store.example,*")

    with pytest.raises(ValidationError, match="API_CORS_ORIGINS"):
        Settings()
