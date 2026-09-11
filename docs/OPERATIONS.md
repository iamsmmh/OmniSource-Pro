# OmniSource operations guide

## Health endpoints and probes

| Endpoint | Purpose | Expected handling |
| --- | --- | --- |
| `GET /health/live` | Process liveness only | Restart only when this fails. |
| `GET /health/ready` | Database + Redis readiness | Returns `503` until dependencies are usable; use for load-balancer readiness. |
| `GET /health` | Owned dependency summary | Returns stable error codes, never driver/provider messages. |
| `GET /health/sources` | Bounded probe of every connector | Probes concurrently, persists sanitized results, and can be slower than readiness. |
| `GET /metrics` | Prometheus exposition | Keep private or protect at the network layer. |

`/health/sources` and the scheduler's source-health task append availability,
latency, error rate, timestamps, and consecutive-failure data to `source_health`.
Raw upstream exceptions are logged with normal access controls and are never
stored in those records or returned by the public health endpoint. The default
cadence is five minutes (`SOURCE_HEALTH_CHECK_INTERVAL=300`) with a 15-second
per-source limit (`SOURCE_HEALTH_CHECK_TIMEOUT=15`).

## Observability

- **Structured logs:** standard output is JSON. Forward it using the platform's
  logging agent; redact credentials at the collector as a second line of
  defense.
- **Prometheus:** `monitoring/prometheus.yml` scrapes the API. The provided
  `alerts.yml` detects scrape failure, elevated 5xx ratio, p95 latency, and
  failed/retrying jobs. Route alerts to the team's pager using your existing
  Alertmanager configuration.
- **Grafana:** Compose mounts the provisioned datasource and `OmniSource
  Overview` dashboard. Set `GRAFANA_ADMIN_PASSWORD`; anonymous access and
  registration are disabled.
- **OpenTelemetry:** set `OTEL_EXPORTER_OTLP_ENDPOINT` to an OTLP/HTTP traces
  endpoint (normally ending in `/v1/traces`) and optionally
  `OTEL_SERVICE_NAME`. The API emits FastAPI spans with service version and
  deployment environment attributes. `/health/live` and `/metrics` are
  excluded from instrumentation noise.
- **Sentry:** set `SENTRY_DSN` to enable exception reporting. The integration
  sets `send_default_pii=false` and does not opt in to request-body or identity
  capture. Configure sampling/redaction policy at the Sentry project as well.

## Background work

The scheduler executes discovery, source sync, validation, indexing,
recommendation refresh, signed-feed generation, source health, and daily backup
cycles. The Celery worker consumes explicitly queued jobs; it uses JSON-only
serialization, late acknowledgements, and a prefetch multiplier of one to
reduce loss/hoarding during a worker failure.

Do not run more than one scheduler replica. The Helm chart enforces one replica
and uses a `Recreate` strategy. For an HA scheduler, replace it with a
leader-elected scheduler rather than merely increasing replicas.

## Data protection and recovery

1. Run `omnisource backup` (or the scheduled backup job) to create PostgreSQL
   dumps and feed snapshots. Store outputs in encrypted object storage outside
   the cluster/host.
2. Test a restore at least quarterly: restore to an isolated PostgreSQL instance,
   run `alembic upgrade head`, start a read-only API, verify an app, feed
   signature, and search index rebuild.
3. PostgreSQL is the source of truth. Meilisearch and local response caches can
   be rebuilt after restore. Redis queues may not be safely replayable without
   idempotency review.
4. Before pruning backups, confirm retention covers the desired recovery-point
   objective. The `BACKUP_KEEP` setting is count-based, not a compliance policy.

## Incident runbooks

### API unavailable

1. Check `/health/live`, then `/health/ready`.
2. If liveness fails, inspect container/pod termination reason and structured
   logs; restart or roll back the application image.
3. If readiness fails, distinguish database and Redis from the stable readiness
   fields. Check private-network connectivity and provider status; do not expose
   a database or Redis port to troubleshoot.
4. Verify the latest migration job completed. A failed migration should block
   rollout rather than being bypassed with manual table creation.

### Elevated 5xx rate

1. Use the Grafana dashboard to identify endpoint and latency correlation.
2. Inspect structured exception logs and Sentry event fingerprints; do not paste
   secrets/provider payloads into tickets.
3. Check database pool saturation, Redis errors, Meilisearch status, and worker
   backlog.
4. Mitigate with rollback, a query-rate limit reduction, or capacity changes.
   Preserve a database snapshot before any data repair.

### Background job failures

1. Query `/api/v1/admin/jobs` with an API key and inspect the bounded job error
   code/message.
2. Check worker health, Redis persistence, and source status. Retry only
   idempotent jobs after the underlying provider/configuration issue is fixed.
3. For repeated artifact-security failures, keep the asset quarantined and
   review evidence before a manual override. Do not automatically allow a
   scanner-disabled result to clear a previous flag.

### Source unavailable

1. Call `/health/sources` from an operator network or wait for the scheduled
   health job; it returns `source_unavailable` rather than raw provider errors.
2. Inspect protected logs for the provider response category (auth, rate limit,
   timeout, parser); check token expiration and upstream incident status.
3. Do not disable rate limiting to clear a backlog. Let retry/recovery windows
   work, reduce discovery batch size if needed, and resume from the persisted
   source checkpoint.

### Feed integrity failure

1. Stop publishing the affected feed channel and retain the last known-good
   atomic feed file.
2. Verify the feed's SHA-256 and Ed25519 signature against the pinned public
   key. Treat a key mismatch as a security incident.
3. Check signing-key access/audit records, rotate keys if compromise is possible,
   publish a new signed feed, and coordinate client pin updates.

## Security operating rules

- Grant separate API keys to OmniStore services and rotate/revoke them without
  rotating `SECRET_KEY` unless subject-hash invalidation is acceptable.
- Keep source, webhook, scanner, and feed-signing secrets separate.
- VirusTotal requests use artifact SHA-256 only; YARA scans only worker-supplied,
  controlled bytes. No arbitrary release binary is downloaded merely to scan it.
- Private collections/favorites use an HMAC-derived subject hash. Do not add raw
  identity, IP address, user agent, or free-form event data to analytics tables.
- Apply dependencies from locked/reviewed builds, scan images in CI, and run
  containers as non-root with read-only root filesystems where supported.
