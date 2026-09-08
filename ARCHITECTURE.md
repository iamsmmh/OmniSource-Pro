# OmniSource Architecture

## Overview

OmniSource is an autonomous, continuously running software discovery, indexing, validation, metadata, release-tracking, feed-generation, and API platform designed to power OmniStore.

## Architecture Diagram

```
                    EXTERNAL SOURCES
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
    GitHub            GitLab           Codeberg
       │                 │                 │
    Forgejo          F-Droid          Flathub
       │                 │                 │
    Winget           Homebrew        Other Sources
       └─────────────────┼─────────────────┘
                         ↓
                 OMNISOURCE INGESTION
                         ↓
              Repository Discovery
                         ↓
                Metadata Extraction
                         ↓
                 Release Detection
                         ↓
                  Asset Detection
                         ↓
                Package Validation
                         ↓
                Security Evaluation
                         ↓
                  Deduplication
                         ↓
                 Categorization
                         ↓
                Quality / Trust Score
                         ↓
                   PostgreSQL
                         ↓
              ┌──────────┴──────────┐
              ↓                     ↓
        Search Index (Meilisearch)    API Layer (FastAPI)
              ↓                     ↓
              └──────────┬──────────┘
                         ↓
                 Feed Generator
                         ↓
                  CDN / Static Feeds
                         ↓
                      OMNISTORE
```

## Components

### 1. Connectors (`omnisource/connectors/`)
Plugin-style architecture for different software sources.

- `base.py` - Abstract base connector
- `github/` - GitHub API connector
- `gitlab/` - GitLab API connector
- `codeberg/` - Codeberg API connector
- `forgejo/` - Forgejo API connector
- `fdroid/` - F-Droid connector
- `flathub/` - Flathub connector
- `winget/` - Winget connector
- `homebrew/` - Homebrew connector

### 2. Crawler (`omnisource/crawler/`)
Discovery and ingestion engine.

- `discovery.py` - Repository discovery logic
- `scheduler.py` - Job scheduling and coordination
- `checkpoint.py` - State persistence and resumption
- `filters.py` - Repository filtering policies
- `policies.py` - Processing policies

### 3. Core Domain (`omnisource/core/`)
Business logic and data models.

- `models/` - Database models
- `schemas/` - Pydantic schemas
- `services/` - Business services
- `repositories/` - Database repositories

### 4. Processing (`omnisource/processing/`)
Data processing pipeline.

- `metadata_extractor.py` - Metadata extraction
- `platform_detector.py` - Platform detection
- `architecture_detector.py` - Architecture detection
- `license_engine.py` - License detection and normalization
- `categorization/` - App categorization
- `deduplication/` - Duplicate detection
- `validation/` - Asset and metadata validation

### 5. Intelligence (`omnisource/intelligence/`)
Optional AI-enhanced features.

- `enhancer.py` - Metadata enhancement
- `trust_scoring.py` - Trust score calculation
- `quality_scoring.py` - Quality score calculation
- `popularity.py` - Popularity calculation
- `relationships.py` - App relationship detection

### 6. Search (`omnisource/search/`)
Search functionality.

- `indexer.py` - Meilisearch indexer
- `query.py` - Search query handling

### 7. API (`omnisource/api/`)
FastAPI application.

- `main.py` - FastAPI app
- `routes/` - API routes
- `dependencies.py` - FastAPI dependencies

### 8. Feeds (`omnisource/feeds/`)
Feed generation.

- `generator.py` - Feed generation logic
- `schemas/` - Feed schemas
- Platform-specific feed generators

### 9. Automation (`omnisource/automation/`)
Job system and scheduling.

- `jobs/` - Job definitions
- `scheduler.py` - Job scheduler
- `worker.py` - Background worker
- `queue.py` - Job queue (Celery + Redis)

### 10. CLI (`omnisource/cli/`)
Command-line interface.

- `main.py` - CLI entry point
- Commands for various operations

## Data Flow

```
1. Discovery: Connector discovers repositories from external sources
2. Ingestion: Crawler fetches repository data
3. Processing: Metadata extraction, platform/architecture detection, etc.
4. Validation: Assets and metadata are validated
5. Deduplication: Duplicate applications are merged
6. Storage: Data persisted to PostgreSQL
7. Indexing: Data indexed in Meilisearch
8. Feed Generation: Platform-specific feeds generated
9. API: Data served via FastAPI
```

## Technology Stack

- **Language**: Python 3.11+
- **Web Framework**: FastAPI
- **Database**: PostgreSQL 15+
- **ORM**: SQLAlchemy 2.x
- **Migrations**: Alembic
- **Search**: Meilisearch
- **Message Queue**: Redis + Celery
- **HTTP Client**: httpx (async)
- **Validation**: Pydantic
- **Type Checking**: pyright
- **Linting**: ruff
- **Testing**: pytest
- **Containerization**: Docker

## Contract with OmniStore

OmniSource provides:
- REST API at `/api/v1/` with endpoints matching OmniStore's expectations
- Static JSON feeds at `/feeds/` for reliable synchronization
- Versioned schemas for backward compatibility

OmniStore consumes:
- App, Release, Asset schemas defined in `src/lib/schemas/omnisource.ts`
- Search, trending, categories, platforms endpoints
- Feed data for offline-capable clients

## Directory Structure

```
omnisource/
├── connectors/
│   ├── __init__.py
│   ├── base.py
│   └── github/
│       ├── __init__.py
│       ├── client.py
│       ├── models.py
│       └── connector.py
├── crawler/
│   ├── __init__.py
│   ├── discovery.py
│   ├── scheduler.py
│   ├── checkpoint.py
│   ├── filters.py
│   └── policies.py
├── core/
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── ...
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── ...
│   └── repositories/
│       ├── __init__.py
│       └── ...
├── processing/
│   ├── __init__.py
│   ├── metadata_extractor.py
│   ├── platform_detector.py
│   ├── architecture_detector.py
│   ├── license_engine.py
│   └── validation/
│       ├── __init__.py
│       ├── url_validator.py
│       ├── asset_validator.py
│       └── checksum.py
├── intelligence/
│   ├── __init__.py
│   ├── enhancer.py
│   ├── trust_scoring.py
│   ├── quality_scoring.py
│   ├── popularity.py
│   └── relationships.py
├── search/
│   ├── __init__.py
│   ├── indexer.py
│   └── query.py
├── api/
│   ├── __init__.py
│   ├── main.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── search.py
│   │   ├── releases.py
│   │   ├── categories.py
│   │   ├── platforms.py
│   │   ├── developers.py
│   │   ├── trending.py
│   │   ├── latest.py
│   │   └── stats.py
│   └── dependencies.py
├── feeds/
│   ├── __init__.py
│   ├── generator.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── v1.py
│   └── platform_feeds/
│       ├── __init__.py
│       ├── ios.py
│       ├── android.py
│       ├── windows.py
│       ├── macos.py
│       └── linux.py
├── automation/
│   ├── __init__.py
│   ├── jobs/
│   │   ├── __init__.py
│   │   ├── discover.py
│   │   ├── sync.py
│   │   ├── validate.py
│   │   ├── index.py
│   │   └── generate_feeds.py
│   ├── scheduler.py
│   ├── worker.py
│   └── queue.py
├── cli/
│   └── main.py
├── config/
│   ├── __init__.py
│   ├── settings.py
│   └── logging.py
├── utils/
│   ├── __init__.py
│   ├── http.py
│   ├── retry.py
│   ├── cache.py
│   └── security.py
├── migrations/
│   └── versions/
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   └── ...
│   └── integration/
│       └── ...
├── scripts/
│   └── entrypoint.sh
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Key Design Principles

1. **Source-Agnostic**: New sources can be added by implementing a connector
2. **Platform-Aware**: Supports iOS, iPadOS, Android, Windows, macOS, Linux
3. **API-First**: All functionality exposed via REST API
4. **Fault Tolerant**: Failures isolated, retries automatic, state persistent
5. **Observable**: Structured logging, metrics, health checks
6. **Secure**: All external input treated as untrusted
7. **Idempotent**: Operations can be safely retried
8. **Scalable**: Designed for 100k+ apps, 500k+ releases, 1M+ assets
9. **Backward Compatible**: Versioned APIs and feeds
10. **Testable**: High test coverage for critical paths
