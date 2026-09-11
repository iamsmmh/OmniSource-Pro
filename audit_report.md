# OmniSource-Pro engineering audit

**Audit date:** 2026-09-11  
**Audited revision:** `b371893e40f4f8269a87faa098da35ee85534e4e` plus the changes in this branch  
**Scope:** backend service, connectors, data model/migrations, automation, API
contracts, feeds, deployment assets, observability, and repository-operational
safety. The OmniStore frontend is not present in this repository and therefore
cannot be audited or shipped from this branch.

## Executive summary

OmniSource-Pro has a viable asynchronous FastAPI/SQLAlchemy foundation with
source connectors, a discovery-to-feed pipeline, a versioned API, and a useful
test suite. This branch closes a number of production gaps: signed channel
feeds, response caching/ETags, rate limiting, a persisted recommendation graph,
pseudonymous favorites/collections/analytics, richer repository enrichment,
security evidence persistence, resilient connector HTTP requests, safe source
health history, an Alembic startup fix, and deployment/observability assets.

It is **not appropriate to describe the product as fully production ready yet**
until the residual items below are addressed and verified in a real staging
environment. In particular, source integrations are mock-tested rather than
live-certified, no generated API-client/TypeScript shared-model package exists
in this repository, and a separate OmniStore frontend repository must complete
its own web/PWA acceptance scope.

## Evidence collected

| Check | Result | Notes |
| --- | --- | --- |
| `ruff format omnisource tests` | Pass | Formatting is canonical. |
| `ruff check omnisource tests` | Pass | Includes security-oriented Ruff rules configured in `pyproject.toml`. |
| `mypy omnisource` | Pass | 186 source files checked under the repository's practical baseline. |
| `pytest -q` with in-memory SQLite | Pass | 113 tests passed. Existing async-marker/deprecation warnings remain. |
| `alembic upgrade head` with a fresh SQLite database | Pass | Reaches revision `0006`. |
| Docker Compose config/build | Not run | Docker is not installed in this audit environment. |
| Helm lint/template | Not run | Helm is not installed in this audit environment. |
| Live provider probes | Not run | Avoided to prevent rate-limit/token side effects; mocked connector coverage exists. |
| Load/soak, restore, and DR drills | Not run | Required before a production launch. |

## Architecture and data flow review

The intended data path is source connector → discovery checkpoint → repository
sync → deterministic enrichment/package detection → release/asset validation →
security evidence → scoring/recommendation edge rebuild → search index/feed/API.
The core state lives in PostgreSQL; response/search caches and Celery transport
use Redis; Meilisearch is a rebuildable secondary index.

### Strengths

- SQLAlchemy 2.x models and Alembic migrations define the primary catalog.
- Connectors are registered by source type and share a common interface.
- Incremental repository sync uses upstream `pushed_at` plus a forced-refresh
  window instead of blindly rereading every release.
- Source discovery progress is checkpointed; connector requests now have
  bounded retries, `Retry-After` handling, and rate-limit bookkeeping.
- Recommendation edge building starts from indexed shared candidates instead of
  a full Python O(n²) catalog scan.
- API rate limiting, API-key checks, CORS allowlisting, ETags, and response
  caching are implemented.

### Findings remediated in this branch

| ID | Severity | Finding | Remediation |
| --- | --- | --- | --- |
| A-01 | High | A standard `alembic upgrade head` required a pre-initialized application engine and failed in clean deployment jobs. | `migrations/env.py` now creates the async engine itself and executes migrations through `run_sync`; clean upgrade to `0006` passed. |
| A-02 | High | API routes and health checks exposed raw exception text, which can include provider paths and configuration details. | Public API failures use stable generic messages; public health/source results are sanitized; raw detail remains only in protected logs. |
| A-03 | High | Compose used hard-coded example credentials, exposed data ports, mounted a nonexistent init script, and started without a migration gate. | Compose requires secrets, keeps data services private, has a one-shot migration service, and blocks workloads on migration success. |
| A-04 | Medium | The Celery app was created only when dispatching; `celery -A ... worker` did not have a stable application object. | A module-level singleton Celery app is now discoverable and uses JSON-only serialization, late acks, and prefetch one. |
| A-05 | Medium | Source checks were ephemeral and only GitHub was checked from the main health code. | All registered sources are probed concurrently with bounds; safe availability/latency/failure history is persisted in `source_health`; a scheduler job runs it. |
| A-06 | Medium | Signed feeds and optional security providers needed stronger type/error handling. | Ed25519 envelope verification is type-safe, OSV degraded results are sanitized, and feed integrity is rechecked before delivery. |
| A-07 | Medium | The Compose file referenced absent monitoring files. | Prometheus rules, Grafana provisioning/dashboard, OpenTelemetry, Sentry configuration hooks, runbooks, and deployment guidance are provided. |

## Connector assessment

| Source | Implementation state | Operational observations |
| --- | --- | --- |
| GitHub | Repository/release/asset/metadata discovery | Authenticated quota strongly recommended; retry policy exists; live API contract needs staging verification. |
| GitLab | Repository/release/asset/metadata discovery | Token handling/retry paths are implemented; verify self-hosted GitLab version compatibility. |
| Codeberg / Forgejo | Gitea-compatible client | Instance URL/version differences require integration certification. |
| F-Droid | Package and APK metadata | Validate against current upstream API/catalog shape and signature policy. |
| Flathub | Appstream/Flatpak data | Validate current v1/v2 response shapes and package references. |
| WinGet | Manifest repository traversal | GitHub API quota and manifest layout changes require monitoring. |
| Homebrew | Formula/cask metadata | Formula/cask schema variants need a scheduled contract fixture refresh. |

All connectors have offline mocked tests, shared retry/rate-limit recovery, and
bounded source health probes. “Implemented” does not substitute for live
acceptance against each provider with production credentials and realistic
catalogue pagination.

## Security and privacy review

### Implemented controls

- Explicit production settings validation requires a non-default service secret,
  API key(s), Meilisearch key, explicit CORS origins, and non-ephemeral Ed25519
  feed key.
- Feed writes are atomic; signed feed envelopes are canonicalized, SHA-256
  hashed, Ed25519-signed, and revalidated before serving.
- Admin operations and personal OmniStore endpoints require API keys. Personal
  identifiers are HMAC-derived before favorite/collection/analytics persistence.
- Analytics dimensions are allowlisted and bounded; no raw identity, IP, or
  user-agent field is modeled.
- VirusTotal lookups use existing SHA-256 hashes only; YARA accepts controlled
  worker bytes rather than downloading arbitrary binaries on request.
- Invalid/flagged security evidence can quarantine an asset.
- Containers run as non-root; Helm workloads use non-root, no privilege
  escalation, dropped capabilities, seccomp, and read-only root filesystems.

### Remaining security actions

1. Add secret scanning, dependency/SBOM generation, image scanning, and signed
   image provenance to CI before publishing images.
2. Define an audited manual quarantine-release/false-positive process. Current
   validation appends scan history each run; retention and idempotency policy
   should be agreed before large-scale operation.
3. Pin a public feed verification key in each OmniStore client and rehearse key
   rotation/revocation.
4. Apply a network policy with explicit DNS, database, cache, search, and
   provider egress controls for the actual CNI/environment.
5. Threat-model webhooks, reverse-proxy limits, administrative access, and
   object-storage feed publication with the deployment owner.

## Scale and reliability review

- The database pool is configurable and SQLite gets development lock pragmas.
- API caching uses a bounded in-process tier and optional Redis tier; cache
  failures degrade to direct requests.
- Recommendation candidate selection is bounded, but rebuilding it per synced
  app and every scheduled batch must be load-tested at catalogue scale.
- Local channel feeds require shared storage when API and scheduler replicas are
  separate. The Helm chart requests RWX storage; multi-region delivery should
  use an independently implemented object-store/CDN publisher.
- Meilisearch is recoverable but index rebuild time, embedder throughput, and
  vector-query latency have not been benchmarked.
- `source_health` is append-only. Add retention/roll-up (for example, hourly
  summaries after 30 days) once expected probe volume is known.

## API and client-contract review

The `/api/v1` route surface covers catalogue apps, search, releases, categories,
platforms, developers, trending/latest/stats, recommendations/similar/discover,
collections, favorites, aggregate analytics, trust, security, and OmniStore
compatibility aliases. OpenAPI remains available at `/openapi.json`; the
response cache adds ETag/Cache-Control to anonymous cacheable GETs.

Residual client work:

1. Generate and version a language-neutral OpenAPI artifact plus a
   `packages/shared-models` TypeScript package (DTOs, Zod schemas, and clients)
   in a controlled monorepo or sibling repository.
2. Contract-test the precise mobile/desktop/web OmniStore responses, pagination,
   304 semantics, error envelopes, and signed feed verification in those
   clients.
3. Document deprecation windows for legacy array-only feeds.

## Release gate

Before launch, require all of the following:

- [ ] CI lint, type check, tests, migration check, image build, SBOM and image
      scan pass on the release SHA.
- [ ] Docker/Helm render and deployment run in staging.
- [ ] Each provider connector passes a credentialed, rate-limit-aware live smoke
      test and pagination resume test.
- [ ] Migration backup/restore and rollback procedures are rehearsed.
- [ ] Load test proves target p95/p99 latency and worker throughput at expected
      catalogue/import volume.
- [ ] Prometheus alert routing, Grafana access, Sentry redaction, and OTLP
      export are observed in staging.
- [ ] Feed public key is pinned in clients and a rotation drill succeeds.
- [ ] OmniStore frontend/mobile/desktop acceptance suites pass against the
      deployed API.

## Conclusion

This branch materially improves safety, operational deployment, connector
recovery, auditability, and API capabilities. It should be merged only after
normal code review and then promoted through staging using the release gate
above. The unresolved items are launch criteria, not cosmetic follow-ups.
