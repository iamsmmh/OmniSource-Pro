"""Job queue abstraction for OmniSource automation."""

import asyncio
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class JobQueue:
    """Abstract job queue interface."""

    async def enqueue(self, item: dict[str, Any]) -> None:
        raise NotImplementedError

    async def dequeue(self) -> dict[str, Any]:
        raise NotImplementedError

    def qsize(self) -> int:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class InProcessJobQueue(JobQueue):
    """In-process async job queue (asyncio.Queue backed)."""

    def __init__(self, maxsize: int = 0):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)

    async def enqueue(self, item: dict[str, Any]) -> None:
        await self._queue.put(item)

    async def dequeue(self) -> dict[str, Any]:
        return await self._queue.get()

    def qsize(self) -> int:
        return self._queue.qsize()

    async def close(self) -> None:
        return None


async def enqueue_job(job: dict[str, Any]) -> str:
    """Dispatch a job for execution.

    Uses the Celery broker when celery is configured (so a separate worker
    process picks it up), otherwise falls back to an in-process queue that a
    locally running AsyncWorker consumes.
    """
    job_id = str(job.get("job_id") or uuid.uuid4())
    job = {**job, "job_id": job_id}

    from omnisource.automation.worker import get_celery_app

    celery_app = get_celery_app()
    if celery_app is not None:
        try:
            celery_app.send_task("omnisource.run_job", args=[job])
            return job_id
        except Exception:
            logger.warning("Celery dispatch failed; falling back to in-process queue")

    await _local_queue().enqueue(job)
    return job_id


_local_queue_instance: InProcessJobQueue | None = None


def _local_queue() -> InProcessJobQueue:
    global _local_queue_instance
    if _local_queue_instance is None:
        _local_queue_instance = InProcessJobQueue()
    return _local_queue_instance


def get_local_queue() -> InProcessJobQueue:
    """Return the shared in-process queue (used by AsyncWorker and enqueue_job)."""
    return _local_queue()


__all__ = ["InProcessJobQueue", "JobQueue", "enqueue_job", "get_local_queue"]
