"""
Settings configuration for OmniSource.

Uses Pydantic Settings with environment variable support.
"""

import json
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://user:password@localhost:5432/omnisource",
        description="PostgreSQL database URL",
    )
    BACKUP_DIR: str = Field(default="./data/backups", description="Backup output directory")
    BACKUP_KEEP: int = Field(default=7, ge=1, description="Backups to retain per artifact type")
    DATABASE_POOL_SIZE: int = Field(default=20, ge=1, le=100)
    DATABASE_MAX_OVERFLOW: int = Field(default=10, ge=0, le=50)
    DATABASE_POOL_TIMEOUT: int = Field(default=30, ge=1, le=300)
    DATABASE_ECHO: bool = Field(default=False)


class RedisSettings(BaseSettings):
    """Redis configuration for caching and message queue."""

    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    REDIS_CACHE_TTL: int = Field(default=3600, ge=0, description="Default cache TTL in seconds")
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/1",
        description="Celery broker URL",
    )
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://localhost:6379/2",
        description="Celery result backend URL",
    )


class MeilisearchSettings(BaseSettings):
    """Meilisearch configuration."""

    MEILISEARCH_URL: str = Field(
        default="http://localhost:7700",
        description="Meilisearch server URL",
    )
    MEILISEARCH_MASTER_KEY: str | None = Field(
        default=None,
        description="Meilisearch master key (optional for development)",
    )
    MEILISEARCH_INDEX_NAME: str = Field(
        default="omnisource_apps",
        description="Meilisearch index name",
    )


class GitHubSettings(BaseSettings):
    """GitHub API configuration."""

    GH_TOKEN: str | None = Field(
        default=None,
        description="GitHub personal access token",
    )
    GH_RATE_LIMIT: int = Field(default=5000, ge=1, description="GitHub API rate limit per hour")
    GH_REQUEST_TIMEOUT: int = Field(default=30, ge=1, le=300)
    GH_RETRY_COUNT: int = Field(default=3, ge=0, le=10)


class SourceSettings(BaseSettings):
    """External source configuration."""

    GITLAB_TOKEN: str | None = Field(default=None)
    CODEBERG_TOKEN: str | None = Field(default=None)
    FORGEJO_TOKEN: str | None = Field(default=None)
    HOMEBREW_API_URL: str = Field(default="https://formulae.brew.sh/api")
    FDROID_API_URL: str = Field(default="https://f-droid.org/api/v1")
    FLATHUB_API_URL: str = Field(default="https://flathub.org/api/v1")
    FMHY_MOBILE_URL: str = Field(
        default="https://fmhy.net/mobile",
        description="fmhy.net mobile page (iOS iPAs section) indexed by the FMHY connector",
    )
    WEBHOOK_SECRET_GITHUB: str | None = Field(default=None)
    WEBHOOK_SECRET_GITLAB: str | None = Field(default=None)
    WEBHOOK_SECRET_GITEA: str | None = Field(default=None)
    SOURCE_HEALTH_CHECK_INTERVAL: int = Field(
        default=300,
        ge=60,
        description="Seconds between persisted external-source health probes",
    )
    SOURCE_HEALTH_CHECK_TIMEOUT: float = Field(
        default=15.0,
        ge=1.0,
        le=60.0,
        description="Per-source health-probe timeout in seconds",
    )


class S3Settings(BaseSettings):
    """S3-compatible storage configuration for feeds."""

    S3_ENDPOINT: str | None = Field(default=None)
    S3_BUCKET: str | None = Field(default=None)
    S3_ACCESS_KEY: str | None = Field(default=None)
    S3_SECRET_KEY: str | None = Field(default=None)
    S3_REGION: str | None = Field(default=None)
    S3_FEEDS_PREFIX: str = Field(default="feeds")


class AISettings(BaseSettings):
    """AI provider configuration (optional)."""

    AI_PROVIDER: str | None = Field(default=None)
    AI_API_KEY: str | None = Field(default=None)
    AI_API_URL: str | None = Field(default=None)
    AI_EMBEDDING_MODEL: str | None = Field(default="text-embedding-3-small")


class ObservabilitySettings(BaseSettings):
    """Optional managed error reporting and distributed tracing configuration."""

    SENTRY_DSN: str | None = Field(default=None)
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = Field(default=None)
    OTEL_SERVICE_NAME: str = Field(default="omnisource")


class APISettings(BaseSettings):
    """API server configuration."""

    # pydantic-settings assumes every ``list`` environment value is JSON. The
    # documented/operator-friendly API_KEYS and API_CORS_ORIGINS values are
    # comma-separated, so decode them below while still accepting JSON arrays.
    model_config = SettingsConfigDict(enable_decoding=False)

    API_HOST: str = Field(default="0.0.0.0")  # noqa: S104 - server binds all interfaces by design
    API_PORT: int = Field(default=8000, ge=1, le=65535)
    API_DEBUG: bool = Field(default=False)
    API_WORKERS: int = Field(default=4, ge=1, le=100)
    API_RATE_LIMIT: int = Field(default=100, ge=1, description="Requests per minute")
    API_KEYS: list[str] = Field(
        default_factory=list,
        description="Valid API keys; empty list disables API-key auth",
    )
    API_AUTH_REQUIRED: bool = Field(
        default=False,
        description="Require an API key on public read endpoints as well",
    )
    API_CORS_ORIGINS: list[str] = Field(
        default_factory=list,
        description="Explicit CORS allowed origins; empty disables browser CORS",
    )
    API_RESPONSE_CACHE_TTL: int = Field(default=60, ge=0, le=3600)
    API_SEARCH_CACHE_TTL: int = Field(default=30, ge=0, le=3600)

    @field_validator("API_KEYS", "API_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_delimited_list(cls, value: Any) -> list[str]:
        """Accept a JSON array or conventional comma-separated environment value."""
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError("must be a JSON array or comma-separated list") from exc
                if not isinstance(parsed, list):
                    raise ValueError("must be a JSON array or comma-separated list")
                value = parsed
            else:
                value = stripped.split(",")
        if not isinstance(value, (list, tuple, set)):
            raise ValueError("must be a JSON array or comma-separated list")
        return [str(item).strip() for item in value if str(item).strip()]


class FeedSettings(BaseSettings):
    """Feed generation and Ed25519 signing configuration."""

    FEEDS_DIR: str = Field(default="./data/feeds", description="Local feeds directory")
    FEEDS_VERSION: str = Field(default="v1", description="Default feed version")
    FEED_GENERATION_INTERVAL: int = Field(
        default=3600,
        ge=60,
        description="Feed regeneration interval in seconds",
    )
    FEED_SIGNING_PRIVATE_KEY: str | None = Field(
        default=None,
        description="PEM or base64 raw Ed25519 private key; required in production",
    )
    FEED_SIGNING_PUBLIC_KEY: str | None = Field(
        default=None,
        description="Optional PEM or base64 raw Ed25519 public key for local verification",
    )
    FEED_ALLOW_EPHEMERAL_SIGNING: bool = Field(
        default=True,
        description="Development-only ephemeral signing fallback; forbidden in production",
    )


class SecuritySettings(BaseSettings):
    """Security scanning and service-secret configuration."""

    SECRET_KEY: str = Field(
        default="change-me-in-production",
        description="Service secret; must be replaced in production",
    )
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=1)
    VIRUSTOTAL_API_KEY: str | None = Field(default=None)
    VIRUSTOTAL_API_URL: str = Field(default="https://www.virustotal.com/api/v3")
    YARA_RULES_DIR: str | None = Field(default=None)


class Settings(BaseSettings):
    """Main OmniSource settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Sub-settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    meilisearch: MeilisearchSettings = Field(default_factory=MeilisearchSettings)
    github: GitHubSettings = Field(default_factory=GitHubSettings)
    sources: SourceSettings = Field(default_factory=SourceSettings)
    s3: S3Settings = Field(default_factory=S3Settings)
    ai: AISettings = Field(default_factory=AISettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    api: APISettings = Field(default_factory=APISettings)
    feeds: FeedSettings = Field(default_factory=FeedSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)

    # General settings
    APP_NAME: str = Field(default="OmniSource")
    APP_VERSION: str = Field(default="0.1.0")
    APP_ENV: str = Field(default="development", description="Application environment")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # Discovery settings
    DISCOVERY_BATCH_SIZE: int = Field(default=100, ge=1, le=1000)
    DISCOVERY_MAX_REPOS: int = Field(default=100000, ge=1)
    DISCOVERY_MIN_STARS: int = Field(default=0, ge=0)

    # Sync settings
    SYNC_INTERVAL_HOURS: int = Field(default=6, ge=1, le=24)
    VALIDATION_INTERVAL_HOURS: int = Field(default=12, ge=1, le=24)
    SYNC_SKIP_UNCHANGED: bool = Field(
        default=True, description="Skip repositories whose pushed_at is unchanged"
    )
    SYNC_MAX_AGE_HOURS: int = Field(
        default=168, ge=1, description="Force a full resync after this many hours"
    )

    @field_validator("APP_ENV")
    @classmethod
    def validate_env(cls, v: str) -> str:
        valid_envs = {"development", "staging", "production"}
        if v.lower() not in valid_envs:
            raise ValueError(f"APP_ENV must be one of {valid_envs}")
        return v.lower()

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Fail closed when an unsafe production configuration is supplied."""
        if self.APP_ENV != "production":
            return self
        insecure = {"", "change-me-in-production", "changeme", "secret", "password"}
        if self.security.SECRET_KEY.strip().lower() in insecure:
            raise ValueError("SECRET_KEY must be supplied through a production secret store")
        if not self.feeds.FEED_SIGNING_PRIVATE_KEY or self.feeds.FEED_ALLOW_EPHEMERAL_SIGNING:
            raise ValueError("an Ed25519 FEED_SIGNING_PRIVATE_KEY is required in production")
        if not self.api.API_KEYS:
            raise ValueError("API_KEYS must contain at least one production integration key")
        if not self.meilisearch.MEILISEARCH_MASTER_KEY:
            raise ValueError("MEILISEARCH_MASTER_KEY is required in production")
        if "*" in self.api.API_CORS_ORIGINS:
            raise ValueError("API_CORS_ORIGINS must not contain '*' in production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Allow reloading settings for testing
def reload_settings() -> Settings:
    """Reload settings, clearing the cache."""
    get_settings.cache_clear()
    return get_settings()
