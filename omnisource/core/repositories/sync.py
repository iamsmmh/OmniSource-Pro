"""Sync state and job repository for OmniSource."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select

from omnisource.core.models.sync import (
    SyncJob,
    SyncJobStatus,
    SyncJobType,
    SyncState,
)
from omnisource.core.repositories.base import BaseRepository


class SyncRepository(BaseRepository[SyncJob]):
    """Repository for sync state and job entities."""

    model = SyncJob

    # --- SyncState -------------------------------------------------------

    async def get_sync_state(
        self,
        source_id: UUID | None = None,
        repository_id: UUID | None = None,
    ) -> SyncState | None:
        """Get sync state for a source and/or repository."""
        result = await self.session.execute(
            select(SyncState).where(
                SyncState.source_id == source_id,
                SyncState.repository_id == repository_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_sync_state(
        self,
        source_id: UUID | None = None,
        repository_id: UUID | None = None,
    ) -> SyncState:
        """Get or create sync state for a source and/or repository."""
        state = await self.get_sync_state(source_id, repository_id)
        if state is None:
            state = SyncState(source_id=source_id, repository_id=repository_id)
            self.session.add(state)
            await self.session.flush()
        return state

    async def update_sync_state(
        self,
        state: SyncState,
        **values,
    ) -> SyncState:
        """Update sync state fields."""
        for key, value in values.items():
            if hasattr(state, key):
                setattr(state, key, value)
        await self.session.flush()
        return state

    # --- SyncJob ---------------------------------------------------------

    async def create_job(
        self,
        job_type: SyncJobType | str,
        source_id: UUID | None = None,
        repository_id: UUID | None = None,
        application_id: UUID | None = None,
        priority: int = 0,
        **extra,
    ) -> SyncJob:
        """Create a new sync job."""
        if isinstance(job_type, str):
            job_type = SyncJobType(job_type)
        job = SyncJob(
            job_id=str(uuid4()),
            job_type=job_type,
            status=SyncJobStatus.PENDING,
            source_id=source_id,
            repository_id=repository_id,
            application_id=application_id,
            priority=priority,
            **extra,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_job(self, job_id: str) -> SyncJob | None:
        """Get a job by job_id string."""
        result = await self.session.execute(select(SyncJob).where(SyncJob.job_id == job_id))
        return result.scalar_one_or_none()

    async def list_pending_jobs(self, limit: int = 50) -> list[SyncJob]:
        """List pending jobs ordered by priority (desc) and creation time."""
        result = await self.session.execute(
            select(SyncJob)
            .where(SyncJob.status == SyncJobStatus.PENDING, SyncJob.is_locked.is_(False))
            .order_by(SyncJob.priority.desc(), SyncJob.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_running(self, job: SyncJob, worker_id: str) -> SyncJob:
        """Mark a job as running and lock it."""
        job.status = SyncJobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        job.worker_id = worker_id
        job.is_locked = True
        job.locked_at = datetime.now(UTC)
        job.locked_by = worker_id
        await self.session.flush()
        return job

    async def mark_completed(self, job: SyncJob, result: dict | None = None) -> SyncJob:
        """Mark a job as completed."""
        job.status = SyncJobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        job.is_locked = False
        if result is not None:
            job.result = result
        if job.started_at is not None:
            job.duration_ms = int((job.completed_at - job.started_at).total_seconds() * 1000)
        await self.session.flush()
        return job

    async def mark_failed(
        self, job: SyncJob, error_message: str, error_code: str | None = None
    ) -> SyncJob:
        """Mark a job as failed (or retrying if retries remain)."""
        job.retry_count += 1
        job.error_message = error_message[:1000]
        job.error_code = error_code
        job.is_locked = False
        if job.retry_count < job.max_retries:
            job.status = SyncJobStatus.RETRYING
        else:
            job.status = SyncJobStatus.FAILED
            job.completed_at = datetime.now(UTC)
        await self.session.flush()
        return job

    async def cancel_job(self, job: SyncJob) -> SyncJob:
        """Cancel a pending job."""
        job.status = SyncJobStatus.CANCELLED
        job.completed_at = datetime.now(UTC)
        job.is_locked = False
        await self.session.flush()
        return job
