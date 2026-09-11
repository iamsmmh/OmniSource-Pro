# OmniSource deployment guide

This guide deploys the API, worker, scheduler, PostgreSQL, Redis, Meilisearch,
and observability stack without publishing data-service ports. It assumes the
operator owns a DNS name and terminates TLS at an ingress controller, load
balancer, or reverse proxy.

## Production prerequisites

- PostgreSQL 15+ with backups and point-in-time recovery enabled.
- Redis 7+ configured with persistence appropriate to the queue's delivery
  guarantees.
- Meilisearch 1.5+ with a private network endpoint and a non-default master key.
- A managed secret store. Do not commit or bake secrets into images, Helm values,
  or CI logs.
- A TLS-terminating reverse proxy which only exposes the API service.
- A ReadWriteMany volume for local feed delivery, or an object-storage/CDN feed
  publisher at the edge. The included chart uses the former.

The application fails closed in `APP_ENV=production` unless `SECRET_KEY`,
`API_KEYS`, `MEILISEARCH_MASTER_KEY`, explicit `API_CORS_ORIGINS`, and an
Ed25519 `FEED_SIGNING_PRIVATE_KEY` are configured. This is intentional.

## Generate secrets

Run these commands on a secure administrator machine, then store the output in
your secret manager:

```bash
# General secrets/API keys (generate separate values for each purpose)
python -c 'import secrets; print(secrets.token_urlsafe(48))'

# Ed25519 feed signing seed (base64-encoded, raw 32 bytes)
python - <<'PY'
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
key = Ed25519PrivateKey.generate()
print(base64.b64encode(key.private_bytes(
    serialization.Encoding.Raw,
    serialization.PrivateFormat.Raw,
    serialization.NoEncryption(),
)).decode())
PY
```

Keep the feed private key in a secret store with a rotation procedure. Clients
should pin its corresponding public key rather than trusting only the key
embedded in a downloaded feed.

## Docker Compose

1. Copy the template and replace every `REPLACE_...` value:

   ```bash
   cp .env.example .env
   chmod 600 .env
   ```

2. Set `API_CORS_ORIGINS` to the exact OmniStore origins and configure provider
   tokens as needed. Do **not** use `*` in production.
3. Build and start the stack:

   ```bash
   docker compose up -d --build
   docker compose ps
   ```

   The one-shot `migrate` service runs `alembic upgrade head` before API,
   worker, and scheduler startup. Inspect it first if the application does not
   start:

   ```bash
   docker compose logs migrate
   docker compose logs -f api worker scheduler
   ```

4. Put only `${API_PORT:-8000}` behind your TLS proxy. PostgreSQL, Redis,
   Meilisearch, Prometheus, and Grafana are intentionally not host-published.
   Use `docker compose exec` or a VPN/bastion for administrative access.
5. Verify from the private network:

   ```bash
   curl -fsS http://api:8000/health/live
   curl -fsS http://api:8000/health/ready
   curl -fsS http://api:8000/metrics | head
   ```

Compose mounts a named `app_data` volume shared by API and scheduler so generated
local feeds are visible to API replicas in this single-host topology. Back this
volume up or configure an external publisher before treating it as durable.

## Kubernetes with Helm

The chart at `deploy/helm/omnisource` deploys:

- a horizontally scalable API deployment and ClusterIP service;
- a worker deployment with late acknowledgements and prefetch one;
- exactly one scheduler deployment (`Recreate` strategy);
- a pre-install/pre-upgrade Alembic Job;
- a configurable HPA, PDB, ingress, optional NetworkPolicy, and a shared feed
  PVC.

Create a secret using references from your secret manager. The keys below are
required by the chart; add source, scanner, webhook, and observability keys as
needed:

```bash
kubectl -n omnistore create secret generic omnisource-secrets \
  --from-literal=DATABASE_URL='postgresql+asyncpg://...' \
  --from-literal=REDIS_URL='redis://...' \
  --from-literal=CELERY_BROKER_URL='redis://...' \
  --from-literal=CELERY_RESULT_BACKEND='redis://...' \
  --from-literal=MEILISEARCH_MASTER_KEY='...' \
  --from-literal=SECRET_KEY='...' \
  --from-literal=API_KEYS='...' \
  --from-literal=FEED_SIGNING_PRIVATE_KEY='...'
```

Render before applying and use a pinned immutable image tag:

```bash
helm lint deploy/helm/omnisource
helm template omnisource deploy/helm/omnisource \
  --namespace omnistore \
  --set image.repository=registry.example.com/omnisource \
  --set image.tag=sha-REPLACE_ME \
  --set existingSecret=omnisource-secrets \
  --set corsOrigins=https://store.example.com > rendered.yaml
kubectl apply --dry-run=server -f rendered.yaml
helm upgrade --install omnisource deploy/helm/omnisource \
  --namespace omnistore --create-namespace \
  --set image.repository=registry.example.com/omnisource \
  --set image.tag=sha-REPLACE_ME \
  --set existingSecret=omnisource-secrets \
  --set corsOrigins=https://store.example.com
```

The chart's default feed PVC asks for `ReadWriteMany`. Supply an RWX-capable
storage class or set `persistence.existingClaim` to a pre-provisioned RWX claim.
Do not run local-file feed delivery across replicas without shared storage.

## Rollout and rollback

1. Take and verify a database backup before each migration.
2. Deploy the migration job and wait for it to succeed before rolling API pods.
3. Use `kubectl rollout status deployment/omnisource-api -n omnistore` and probe
   `/health/ready` through the service.
4. Roll back application images with `helm rollback` only after checking the
   migration's downgrade/forward-compatibility notes. Database migrations are
   not automatically reversed.
5. Regenerate feeds after a rollback if any feed schema or signing-key change
   was involved.

See [OPERATIONS.md](OPERATIONS.md) for alerts, backups, source-probe behaviour,
and incident runbooks.
