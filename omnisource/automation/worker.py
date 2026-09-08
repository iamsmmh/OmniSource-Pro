"""Background worker for OmniSource automation."""

import asyncio
import os
import uuid as uuid_mod
from datetime import datetime, UTC
from typing import Any, Dict, Optional

from omnisource.automation.jobs import JOB_HANDLERS
from omnisource.automation.queue import InProcessJobQueue, JobQueue
from omnisource.config.logging import get_logger
from omnisource.core.database.session import create_session

logger = get_logger(__name__)


class AsyncWorker:
    """Pulls jobs from a queue and executes the matching handler."""

    def __init__(
        self,
        queue: Optional[JobQueue] = None,
        worker_id: Optional[str] = None,
        poll_interval: float = 1.0,
    ):
        self.queue = queue or InProcessJobQueue()
        self.worker_id = worker_id or f"worker-{os.getpid()}-{uuid_mod.uuid4().hex[:6]}"
        self.poll_interval = poll_interval
        self._running = False

    async def process_job(self, job: Dict[str, Any]) -> Any:
        """Execute a single job and return its result."""
        job_type = job.get("type") or job.get("job_type")
        handler = JOB_HANDLERS.get(job_type)
        if handler is None:
            logger.warning("No handler registered for job type: %s", job_type)
            return None

        payload = job.get("payload") or job.get("kwargs") or {}
        async with create_session() as session:
            return await handler(session, **payload)

    async def run(self) -> None:
        """Run the worker loop until stopped."""
        self._running = True
        logger.info("Worker %s started", self.worker_id)
        try:
            while self._running:
                job = await self.queue.dequeue()
                try:
                    await self.process_job(job)
                except Exception as exc:  # noqa: BLE001 - worker must survive
                    logger.error(
                        "Job %s failed: %s",
                        job.get("type", job.get("job_type", "unknown")),
                        exc,
                    )
        except asyncio.CancelledError:
            logger.info("Worker %s cancelled", self.worker_id)
            raise
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False


# --- Celery integration (optional) -------------------------------------

def get_celery_app():
    """Return a Celery app if celery is installed, else None."""
    try:
        from celery import Celery  # noqa: PLC0415 - lazy import

        from omnisource.config.settings import get_settings

        settings = get_settings()
        app = Celery(
            "omnisource",
            broker=settings.redis.CELERY_BROKER_URL,
            backend=settings.redis.CELERY_RESULT_BACKEND,
        )
        return app
    except ImportError:
        return None


app = None


__all__ = ["AsyncWorker", "get_celery_app", "app"]
