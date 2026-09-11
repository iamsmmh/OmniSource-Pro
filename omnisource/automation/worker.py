"""Background worker and Celery application for OmniSource automation."""

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
    """Pulls jobs from an in-process queue and invokes registered handlers."""

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
        """Execute one queued job with transaction and Prometheus accounting."""
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
        except Exception:
            record_job(job_type, "failed", time.perf_counter() - started)
            logger.exception("Job %s failed", job_type)
            raise
        finally:
            JOBS_RUNNING.dec()

    async def run(self) -> None:
        """Run the local worker loop until it receives a stop signal."""
        self._running = True
        logger.info("Worker %s started", self.worker_id)
        try:
            while self._running:
                job = await self.queue.dequeue()
                try:
                    await self.process_job(job)
                except Exception:
                    logger.exception(
                        "Job %s failed", job.get("type", job.get("job_type", "unknown"))
                    )
        except asyncio.CancelledError:
            logger.info("Worker %s cancelled", self.worker_id)
            raise
        finally:
            self._running = False

    def stop(self) -> None:
        """Signal a local worker to stop after its current job."""
        self._running = False


# --- Celery integration ---------------------------------------------------------
# Keep a module-level Celery object. `celery -A omnisource.automation.worker`
# imports this name directly; creating a client only inside `enqueue_job` left
# the production Compose worker without a discoverable application.
app: Any | None = None


def get_celery_app() -> Any | None:
    """Return the singleton Celery app, or ``None`` when Celery is unavailable."""
    global app
    if app is not None:
        return app
    try:
        from celery import Celery

        from omnisource.config.settings import get_settings

        settings = get_settings()
        celery_app = Celery(
            "omnisource",
            broker=settings.redis.CELERY_BROKER_URL,
            backend=settings.redis.CELERY_RESULT_BACKEND,
        )
        celery_app.conf.update(
            task_serializer="json",
            result_serializer="json",
            accept_content=["json"],
            task_track_started=True,
            worker_prefetch_multiplier=1,
            task_acks_late=True,
        )

        @celery_app.task(name="omnisource.run_job")
        def run_job(job: dict[str, Any]) -> Any:  # pragma: no cover - runs in a Celery process
            """Execute one job in the synchronous Celery task boundary."""
            worker = AsyncWorker(queue=None)
            return asyncio.run(worker.process_job(job))

        app = celery_app
        return app
    except ImportError:
        return None


# Celery needs this concrete module attribute during worker/beat startup.
app = get_celery_app()


__all__ = ["AsyncWorker", "app", "get_celery_app"]
