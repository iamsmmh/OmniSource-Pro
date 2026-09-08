"""Job queue abstraction for OmniSource automation."""

import asyncio
from typing import Any, Dict, Optional


class JobQueue:
    """Abstract job queue interface."""

    async def enqueue(self, item: Dict[str, Any]) -> None:
        raise NotImplementedError

    async def dequeue(self) -> Dict[str, Any]:
        raise NotImplementedError

    def qsize(self) -> int:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class InProcessJobQueue(JobQueue):
    """In-process async job queue (asyncio.Queue backed)."""

    def __init__(self, maxsize: int = 0):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)

    async def enqueue(self, item: Dict[str, Any]) -> None:
        await self._queue.put(item)

    async def dequeue(self) -> Dict[str, Any]:
        return await self._queue.get()

    def qsize(self) -> int:
        return self._queue.qsize()

    async def close(self) -> None:
        return None


__all__ = ["JobQueue", "InProcessJobQueue"]
