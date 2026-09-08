"""In-process asynchronous task scheduler."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, List

from omnisource.config.logging import get_logger

logger = get_logger(__name__)

TaskFn = Callable[[], Awaitable[Any]]


@dataclass
class ScheduledTask:
    """A periodic task registered with the scheduler."""

    name: str
    interval_seconds: float
    fn: TaskFn
    next_run: float = field(default=0.0)
    last_run: float = field(default=0.0)
    last_error: str | None = None
    runs: int = 0


class AsyncScheduler:
    """Runs periodic async tasks in a single event loop."""

    def __init__(self):
        self._tasks: List[ScheduledTask] = []
        self._running = False

    def add_task(self, name: str, interval_seconds: float, fn: TaskFn) -> ScheduledTask:
        """Register a periodic task."""
        task = ScheduledTask(name=name, interval_seconds=interval_seconds, fn=fn)
        self._tasks.append(task)
        return task

    async def run_once(self, task: ScheduledTask) -> None:
        """Execute a single task and record the result."""
        start = time.monotonic()
        try:
            await task.fn()
            task.runs += 1
            task.last_error = None
            logger.debug(
                "task %s completed in %.2fs",
                task.name,
                time.monotonic() - start,
            )
        except Exception as exc:  # noqa: BLE001 - scheduler must not die
            task.last_error = str(exc)
            logger.error("task %s failed: %s", task.name, exc)
        finally:
            task.last_run = time.monotonic()

    async def run_forever(self) -> None:
        """Run the scheduler loop until stopped."""
        self._running = True
        logger.info("Scheduler started with %d tasks", len(self._tasks))
        try:
            while self._running:
                now = time.monotonic()
                for task in self._tasks:
                    if now >= task.next_run:
                        await self.run_once(task)
                        task.next_run = now + task.interval_seconds
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
            raise
        finally:
            self._running = False

    def stop(self) -> None:
        """Signal the scheduler to stop."""
        self._running = False


__all__ = ["AsyncScheduler", "ScheduledTask"]
