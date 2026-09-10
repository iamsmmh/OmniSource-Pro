"""Background worker for OmniSource automation."""

import asyncio
import os
import uuid as uuid_mod
from typing import Any

from omnisource.automation.jobs import JOB_HANDLERS
from omnisource.automation.queue import JobQueue, get_local_queue
from omnisource.config.logging import get_logger
from omnisource.core.database.session import create_session

logger = get_logger(__name__)


class AsyncWorker:
    """Pulls jobs from a queue and executes the matching handler."""

    def __init__(
        self,
        queue: JobQueue | None = None,
        worker_id: str | None = None,
        poll_interval: float = 1.0,
    ):
        self.queue = queue or get_local_queue()
        self.worker_id = worker_id or f"worker-{os.getpid()}-{uuid_mod.uuid4().hex[:6]}"
        self.poll_interval = poll_interval
        self._running = False

    async def process_job(self, job: dict[str, Any]) -> Any:
        """Execute a single job and return its result."""
        import time

        from omnisource.api.metrics import JOBS_RUNNING, record_job

        job_type = str(job.get("type") or job.get("job_type") or "")
        handler = JOB_HANDLERS.get(job_type)
        if handler is None:
            logger.warning("No handler registered for job type: %s", job_type)
            record_job(job_type or "unknown", "unhandled")
            return None

        payload = job.get("payload") or job.get("kwargs") or {}
        started = time.perf_counter()
        JOBS_RUNNING.inc()
        try:
            async with create_session() as session:
                result = await handler(session, **payload)
            record_job(job_type, "completed", time.perf_counter() - started)
            return result
        except Exception as exc:
            record_job(job_type, "failed", time.perf_counter() - started)
            logger.exception("Job %s failed: %s", job_type, exc)
            raise
        finally:
            JOBS_RUNNING.dec()

    async def run(self) -> None:
        """Run the worker loop until stopped."""
        self._running = True
        logger.info("Worker %s started", self.worker_id)
        try:
            while self._running:
                job = await self.queue.dequeue()
                try:
                    await self.process_job(job)
                except Exception as exc:
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
        from celery import Celery

        from omnisource.config.settings import get_settings

        settings = get_settings()
        app = Celery(
            "omnisource",
            broker=settings.redis.CELERY_BROKER_URL,
            backend=settings.redis.CELERY_RESULT_BACKEND,
        )

        @app.task(name="omnisource.run_job")
        def run_job(job: dict):  # pragma: no cover - exercised by workers
            """Execute a dispatched job inside the Celery worker process."""
            import asyncio

            worker = AsyncWorker(queue=None)
            return asyncio.run(worker.process_job(job))

        return app
    except ImportError:
        return None


app = None


__all__ = ["AsyncWorker", "app", "get_celery_app"]
