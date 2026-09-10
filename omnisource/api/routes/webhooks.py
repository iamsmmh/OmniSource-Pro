"""Inbound webhook ingestion for near-real-time source updates.

Receives GitHub/GitLab/Gitea push & release webhooks, verifies their HMAC
signatures, and enqueues incremental sync jobs so release detection no longer
waits for the next crawl cycle.

Configuration:

- ``WEBHOOK_SECRET_GITHUB`` / ``WEBHOOK_SECRET_GITLAB`` / ``WEBHOOK_SECRET_GITEA``
  (settings.sources) - shared secrets used to verify signature headers.
- Signature headers: ``X-Hub-Signature-256`` (GitHub, ``sha256=<hex>``),
  ``X-Gitlab-Token`` (GitLab, plain token), ``X-Gitea-Signature`` (hex).

Events handled:

- GitHub: ``push``, ``release`` (published/released)
- GitLab: ``Push Hook``, ``Tag Push Hook``, ``Release Hook``
- Gitea/Forgejo: ``push``, ``release``
"""

import hashlib
import hmac
import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.api.dependencies import get_db
from omnisource.automation.queue import enqueue_job
from omnisource.config.logging import get_logger
from omnisource.config.settings import get_settings
from omnisource.core.repositories.repository import RepositoryRepository
from omnisource.core.repositories.sync import SyncRepository

logger = get_logger(__name__)

router = APIRouter()


def _verify_github_signature(payload: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature.removeprefix("sha256="), expected)


def _verify_hex_signature(payload: bytes, signature: str | None, secret: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def _verify_gitlab_token(token_header: str | None, secret: str) -> bool:
    return bool(token_header) and hmac.compare_digest(token_header or "", secret)


async def _read_json(request: Request) -> dict[str, Any]:
    body = await request.body()
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from e
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="Expected a JSON object")
    return parsed


def _repo_slug_from_github(payload: dict[str, Any]) -> str | None:
    repo = payload.get("repository") or {}
    return repo.get("full_name") or None


def _repo_slug_from_gitlab(payload: dict[str, Any]) -> str | None:
    project = payload.get("project") or {}
    return project.get("path_with_namespace") or None


def _repo_slug_from_gitea(payload: dict[str, Any]) -> str | None:
    repo = payload.get("repository") or {}
    return repo.get("full_name") or None


async def _enqueue_sync(session: AsyncSession, source_type: str, slug: str, event: str) -> str:
    """Ensure repository rows exist and enqueue an incremental sync job."""
    from omnisource.core.models.source import SourceType
    from omnisource.core.repositories.source import SourceRepository

    source_repo = SourceRepository(session)
    source = await source_repo.get_by_type(SourceType(source_type))
    if source is None:
        # Webhook for a source we have not crawled yet: register it on the fly.
        source = await source_repo.ensure_default(
            name=source_type.title(),
            source_type=SourceType(source_type),
            base_url=f"https://{source_type}.com",
            is_active=True,
        )
        await session.commit()

    repository_repo = RepositoryRepository(session)
    repository = await repository_repo.get_by(full_name=slug, source_id=source.id)
    if repository is None:
        # Unknown repository: record it so the sync job can fetch it fresh.
        repository = await repository_repo.create(
            source_id=source.id,
            external_id=slug,
            full_name=slug,
            name=slug.rsplit("/", 1)[-1],
            html_url=f"https://{source_type}.com/{slug}"
            if source_type in {"github", "gitlab"}
            else slug,
        )
        await session.commit()

    sync_repo = SyncRepository(session)
    job = await sync_repo.create_job(
        job_type="sync_releases",
        source_id=source.id,
        repository_id=repository.id,
    )
    await session.commit()

    await enqueue_job(
        {
            "type": "sync_releases",
            "payload": {"source_type": source_type, "full_name": slug},
            "job_id": str(job.id),
        }
    )
    logger.info("Webhook %s/%s enqueued sync for %s", source_type, event, slug)
    return str(job.id)


@router.post("/github")
async def github_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict[str, Any]:
    """Receive GitHub push/release webhooks."""
    settings = get_settings()
    secret = getattr(settings.sources, "WEBHOOK_SECRET_GITHUB", None)
    body = await request.body()
    if not secret:
        raise HTTPException(status_code=503, detail="GitHub webhook secret not configured")
    if not _verify_github_signature(body, x_hub_signature_256, secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = json.loads(body)
    event = x_github_event or "unknown"
    if event not in {"push", "release"}:
        return {"status": "ignored", "event": event}

    slug = _repo_slug_from_github(payload)
    if not slug:
        raise HTTPException(status_code=400, detail="Missing repository.full_name")

    job_id = await _enqueue_sync(session, "github", slug, event)
    return {"status": "accepted", "event": event, "repository": slug, "job_id": job_id}


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
    x_gitlab_token: str | None = Header(default=None),
    x_gitlab_event: str | None = Header(default=None),
) -> dict[str, Any]:
    """Receive GitLab push/tag/release webhooks."""
    settings = get_settings()
    secret = getattr(settings.sources, "WEBHOOK_SECRET_GITLAB", None)
    if not secret:
        raise HTTPException(status_code=503, detail="GitLab webhook secret not configured")
    if not _verify_gitlab_token(x_gitlab_token, secret):
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    payload = await _read_json(request)
    event = x_gitlab_event or payload.get("object_kind", "unknown")
    if event not in {"Push Hook", "Tag Push Hook", "Release Hook"}:
        return {"status": "ignored", "event": event}

    slug = _repo_slug_from_gitlab(payload)
    if not slug:
        raise HTTPException(status_code=400, detail="Missing project.path_with_namespace")

    job_id = await _enqueue_sync(session, "gitlab", slug, event)
    return {"status": "accepted", "event": event, "repository": slug, "job_id": job_id}


@router.post("/gitea")
@router.post("/forgejo")
async def gitea_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
    x_gitea_signature: str | None = Header(default=None),
    x_gitea_event: str | None = Header(default=None),
) -> dict[str, Any]:
    """Receive Gitea/Forgejo (incl. Codeberg) push/release webhooks."""
    settings = get_settings()
    secret = getattr(settings.sources, "WEBHOOK_SECRET_GITEA", None)
    body = await request.body()
    if not secret:
        raise HTTPException(status_code=503, detail="Gitea webhook secret not configured")
    if not _verify_hex_signature(body, x_gitea_signature, secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = json.loads(body)
    event = x_gitea_event or "unknown"
    if event not in {"push", "release"}:
        return {"status": "ignored", "event": event}

    slug = _repo_slug_from_gitea(payload)
    if not slug:
        raise HTTPException(status_code=400, detail="Missing repository.full_name")

    job_id = await _enqueue_sync(session, "codeberg", slug, event)
    return {"status": "accepted", "event": event, "repository": slug, "job_id": job_id}


__all__ = ["router"]
