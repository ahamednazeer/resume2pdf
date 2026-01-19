"""Background job management service."""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Any


class JobStatus(str, Enum):
    """Status of a background job."""

    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


@dataclass
class Job:
    """Represents a background job for PDF generation."""

    id: str
    token: str
    status: JobStatus = JobStatus.pending
    progress: int = 0  # 0-100
    result: bytes | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert job to dictionary for API response."""
        return {
            "id": self.id,
            "token": self.token,
            "status": self.status.value,
            "progress": self.progress,
            "error": self.error,
            "has_result": self.result is not None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class JobManager:
    """
    Manages background jobs for PDF generation.

    Parameters
    ----------
    max_jobs : int
        Maximum number of jobs to keep in memory. Default is 1000.
    job_ttl_seconds : int
        Time-to-live for completed/failed jobs. Default is 1 hour.
    """

    max_jobs: int = 1000
    job_ttl_seconds: int = 3600
    _jobs: dict[str, Job] = field(default_factory=dict, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def create_job(self, token: str) -> Job:
        """
        Create a new job for the given token.

        Parameters
        ----------
        token : str
            The rendering token for the resume.

        Returns
        -------
        Job
            The created job instance.
        """
        with self._lock:
            # Clean up old jobs if at capacity
            if len(self._jobs) >= self.max_jobs:
                self._cleanup_old_jobs()

            job_id = str(uuid.uuid4())
            job = Job(id=job_id, token=token)
            self._jobs[job_id] = job
            return job

    def get_job(self, job_id: str) -> Job | None:
        """
        Get a job by ID.

        Parameters
        ----------
        job_id : str
            The job ID.

        Returns
        -------
        Job | None
            The job if found, None otherwise.
        """
        with self._lock:
            return self._jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        status: JobStatus | None = None,
        progress: int | None = None,
        result: bytes | None = None,
        error: str | None = None,
    ) -> Job | None:
        """
        Update a job's status and/or result.

        Parameters
        ----------
        job_id : str
            The job ID.
        status : JobStatus | None
            New status for the job.
        progress : int | None
            Progress percentage (0-100).
        result : bytes | None
            The generated PDF bytes.
        error : str | None
            Error message if failed.

        Returns
        -------
        Job | None
            The updated job if found, None otherwise.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None

            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = progress
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error

            job.updated_at = datetime.now(timezone.utc)
            return job

    def _cleanup_old_jobs(self) -> None:
        """Remove old completed/failed jobs."""
        current_time = datetime.now(timezone.utc)
        to_remove = []

        for job_id, job in self._jobs.items():
            if job.status in (JobStatus.completed, JobStatus.failed):
                age = (current_time - job.updated_at).total_seconds()
                if age > self.job_ttl_seconds:
                    to_remove.append(job_id)

        for job_id in to_remove:
            del self._jobs[job_id]

    def stats(self) -> dict[str, Any]:
        """Get job manager statistics."""
        with self._lock:
            status_counts = {}
            for job in self._jobs.values():
                status_counts[job.status.value] = status_counts.get(job.status.value, 0) + 1

            return {
                "total_jobs": len(self._jobs),
                "max_jobs": self.max_jobs,
                "status_counts": status_counts,
            }


# Global job manager instance
job_manager = JobManager()
