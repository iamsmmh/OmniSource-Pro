"""
Settings configuration for OmniSource.

Uses Pydantic Settings with environment variable support.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://user:password@localhost:5432/omnisource",
        description="PostgreSQL database URL",
    )
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
    WEBHOOK_SECRET_GITHUB: str | None = Field(default=None)
    WEBHOOK_SECRET_GITLAB: str | None = Field(default=None)
    WEBHOOK_SECRET_GITEA: str | None = Field(default=None)


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


class APISettings(BaseSettings):
    """API server configuration."""

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
        default=["*"],
        description="CORS allowed origins",
    )


class FeedSettings(BaseSettings):
    """Feed generation configuration."""

    FEEDS_DIR: str = Field(default="./data/feeds", description="Local feeds directory")
    FEEDS_VERSION: str = Field(default="v1", description="Default feed version")
    FEED_GENERATION_INTERVAL: int = Field(
        default=3600,
        ge=60,
        description="Feed regeneration interval in seconds",
    )


class SecuritySettings(BaseSettings):
    """Security configuration."""

    SECRET_KEY: str = Field(
        default="change-me-in-production",
        description="Secret key for JWT and other security purposes",
    )
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=1)


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

    @field_validator("APP_ENV")
    @classmethod
    def validate_env(cls, v: str) -> str:
        valid_envs = {"development", "staging", "production"}
        if v.lower() not in valid_envs:
            raise ValueError(f"APP_ENV must be one of {valid_envs}")
        return v.lower()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Allow reloading settings for testing
def reload_settings() -> Settings:
    """Reload settings, clearing the cache."""
    get_settings.cache_clear()
    return get_settings()
