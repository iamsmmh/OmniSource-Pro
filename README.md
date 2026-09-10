# OmniSource

> **Autonomous Open-Source Software Discovery, Indexing, Validation, Metadata, and Distribution Platform**

OmniSource is the intelligent backend platform that powers [OmniStore](https://github.com/iamsmmh/OmniStore-Pro). It automatically discovers, indexes, validates, and distributes open-source software metadata across multiple platforms.

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Meilisearch 1.5+
- Docker & Docker Compose (optional)

### Using Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/iamsmmh/OmniSource-Pro.git
cd OmniSource-Pro

# Copy environment file
cp .env.example .env

# Edit .env with your configuration
nano .env

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f api

# Run CLI commands
docker-compose exec api omnisource --help
```

### Using Python Directly

```bash
# Install dependencies
pip install -r requirements.txt

# Or using Poetry
pip install poetry
poetry install

# Initialize database
python main.py bootstrap

# Run migrations
python main.py migrate

# Start API server
python main.py api --reload

# In another terminal, start worker
docker-compose up -d redis
celery -A omnisource.automation.worker worker --loglevel info

# In another terminal, start scheduler
celery -A omnisource.automation.worker beat --loglevel info
```

## ⚙️ Configuration

Copy `.env.example` to `.env` and configure:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/omnisource

# GitHub Token (required for full functionality)
GH_TOKEN=your-github-personal-access-token

# Redis
REDIS_URL=redis://localhost:6379/0

# Meilisearch
MEILISEARCH_URL=http://localhost:7700
MEILISEARCH_MASTER_KEY=your-master-key

# API
API_PORT=8000
API_DEBUG=true
```

## 🏗️ Architecture

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

## 📡 API Endpoints

### v1 Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/apps` | List applications with filtering |
| GET | `/api/v1/apps/{id}` | Get specific application |
| GET | `/api/v1/search` | Search applications |
| GET | `/api/v1/releases` | List releases |
| GET | `/api/v1/categories` | List categories |
| GET | `/api/v1/platforms` | List platforms |
| GET | `/api/v1/developers` | List developers |
| GET | `/api/v1/trending` | Get trending applications |
| GET | `/api/v1/latest` | Get latest applications |
| GET | `/api/v1/stats` | Get statistics |
| GET | `/api/v1/search?semantic=true` | Hybrid search (keyword + embeddings) |
| POST | `/api/v1/webhooks/github` | GitHub webhook ingestion (HMAC-verified) |
| POST | `/api/v1/webhooks/gitlab` | GitLab webhook ingestion |
| POST | `/api/v1/webhooks/gitea` | Gitea/Forgejo/Codeberg webhook ingestion |
| GET | `/api/v1/admin/overview` | Pipeline overview (API key required) |
| GET | `/api/v1/admin/jobs` | Recent sync jobs (API key required) |
| GET | `/api/v1/admin/quarantine` | Quarantine review queue (API key required) |
| POST | `/api/v1/admin/jobs/{id}/retry` | Retry a failed job (API key required) |
| GET/POST/DELETE | `/api/v1/admin/notifications` | Outbound webhook subscriptions (API key required) |
| GET | `/admin` | Admin dashboard UI |

### Health Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Full health check |
| GET | `/health/live` | Liveness probe |
| GET | `/health/ready` | Readiness probe |
| GET | `/health/sources` | Source health status |
| GET | `/metrics` | Prometheus metrics |

### Feed Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/feeds/v1/ios.json` | iOS feed |
| GET | `/feeds/v1/android.json` | Android feed |
| GET | `/feeds/v1/windows.json` | Windows feed |
| GET | `/feeds/v1/macos.json` | macOS feed |
| GET | `/feeds/v1/linux.json` | Linux feed |
| GET | `/feeds/v1/all.json` | All platforms feed |

## 🎯 Features

### ✅ Implemented

- **Database Models**: Complete SQLAlchemy 2.x models for all entities
- **Connectors**: GitHub, GitLab, Codeberg, Forgejo, F-Droid, Flathub, Winget, Homebrew
- **Configuration**: Pydantic-based settings with environment variable support
- **API Framework**: FastAPI with OpenAPI documentation
- **Logging**: Structured JSON logging with configurable levels
- **Docker Support**: Production-ready Docker images and Compose configuration
- **CLI**: Command-line interface for management tasks
- **Processing Pipeline**: Metadata extraction, platform detection, validation
- **Search Integration**: Meilisearch indexing plus optional semantic re-ranking
- **Feed Generation**: Platform-specific feed generation
- **Automation**: Celery-or-in-process job queue and scheduling
- **Intelligence**: Trust scoring, quality scoring, categorization
- **API Security**: API-key auth (constant-time compare) on admin routes
- **Rate Limiting**: Redis-backed limiter with in-memory fallback, standard headers
- **Webhook Ingestion**: HMAC-verified GitHub/GitLab/Gitea webhooks trigger incremental syncs
- **Push Notifications**: Signed outbound webhooks (release.created, feed.updated, ...)
- **Security Scanning**: OSV.dev vulnerability checks, checksum sidecars, signature detection
- **Delta Sync**: `pushed_at`-based skip logic with weekly forced refresh
- **Changelog Analysis**: semver + release-notes breaking-change detection per release
- **Admin Dashboard**: dependency-free HTML UI at `/admin` (jobs, quarantine, sources, retries)
- **Observability**: Prometheus `/metrics` (HTTP, jobs, connectors)
- **Backups**: `omnisource backup` — pg_dump + feed snapshots with retention pruning
- **CI/CD**: GitHub Actions (ruff, mypy, pytest matrix, Docker build)

### 📋 Planned

- **Advanced Deduplication**: ML-based duplicate detection
- **pgvector Storage**: swap JSON embeddings for pgvector at >100k apps
- **AI Enhancement**: Optional AI-powered metadata improvement
- **Monitoring**: Prometheus metrics and Grafana dashboards
- **Scaling**: Horizontal scaling and load balancing

## 📦 Supported Platforms

| Platform | Package Types | Status |
|----------|---------------|--------|
| iOS | `.ipa` | ✅ Supported |
| iPadOS | `.ipa` | ✅ Supported |
| Android | `.apk`, `.aab` | ✅ Supported |
| Windows | `.exe`, `.msi`, `.msix`, `.appx`, `.zip` | ✅ Supported |
| macOS | `.dmg`, `.pkg`, `.zip` | ✅ Supported |
| Linux | `.AppImage`, `.deb`, `.rpm`, `.flatpak`, `.flatpakref`, `.tar.gz` | ✅ Supported |

## 🔧 Supported Sources

| Source | Status | Priority |
|--------|--------|----------|
| GitHub | ✅ Implemented | #1 |
| GitLab | 📋 Planned | #2 |
| Codeberg | 📋 Planned | #3 |
| Forgejo | 📋 Planned | #4 |
| F-Droid | 📋 Planned | #5 |
| Flathub | 📋 Planned | #6 |
| Winget | 📋 Planned | #7 |
| Homebrew | 📋 Planned | #8 |

## 🛠️ Development

### Project Structure

```
omnisource/
├── connectors/           # Source connectors
│   ├── base.py          # Base connector interface
│   └── github/          # GitHub connector
│       ├── client.py    # HTTP client
│       ├── connector.py # Connector implementation
│       └── models.py    # GitHub-specific models
├── core/               # Core domain
│   ├── models/         # Database models
│   ├── schemas/        # Pydantic schemas
│   └── repositories/   # Database repositories
├── api/                # FastAPI application
│   └── routes/         # API routes
├── automation/         # Background jobs
├── cli/                # Command-line interface
├── config/             # Configuration
└── utils/              # Utilities
```

### Running Tests

```bash
# Install test dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=omnisource --cov-report=html

# Run specific test
pytest tests/unit/test_github_connector.py -v
```

### Type Checking

```bash
# Install mypy
pip install mypy

# Run type checking
mypy omnisource/
```

### Linting

```bash
# Install ruff
pip install ruff

# Run linting
ruff check omnisource/

# Auto-fix issues
ruff check --fix omnisource/
```

## 📊 Database Schema

OmniSource uses PostgreSQL with the following main entities:

- **Source**: External software sources (GitHub, GitLab, etc.)
- **Repository**: Software repositories from external sources
- **Application**: Logical applications (may span multiple repositories)
- **Developer/Organization**: Application authors and maintainers
- **License**: Software licenses with SPDX support
- **Platform/Architecture**: Supported platforms and CPU architectures
- **Category/Tag**: Application categorization
- **Release**: Software releases
- **Asset**: Downloadable files (binaries, packages)
- **Screenshot/Icon**: Application media
- **Scores**: Trust, quality, and popularity scores
- **Validation**: Validation results
- **Sync**: Synchronization state and jobs
- **Quarantine**: Quarantined applications
- **Security**: Security scan results

## 🤝 OmniStore Integration

OmniSource provides:

1. **REST API**: Versioned HTTP API at `/api/v1/`
2. **Static Feeds**: JSON feeds at `/feeds/v1/`
3. **Compatible Schemas**: Data schemas matching OmniStore expectations

OmniStore can consume data from:
- REST API endpoints for dynamic data
- Static feeds for reliable offline synchronization

## 📝 License

OmniSource is licensed under the **AGPL-3.0** license. See [LICENSE](LICENSE) for details.

## 🙏 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/iamsmmh/OmniSource-Pro/issues)
- **Discussions**: [GitHub Discussions](https://github.com/iamsmmh/OmniSource-Pro/discussions)
- **Documentation**: [OmniSource Docs](https://github.com/iamsmmh/OmniSource-Pro#readme)

## 🏆 Acknowledgments

- Inspired by the need for a unified open-source software catalog
- Built to power [OmniStore](https://github.com/iamsmmh/OmniStore-Pro)
- Thanks to all contributors and the open-source community
