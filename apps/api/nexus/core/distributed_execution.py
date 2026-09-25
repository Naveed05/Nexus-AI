from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from .distributed_workers import WorkerCoordinator
from .jobs import DurableJob, JobStatus, JobStore


@dataclass(frozen=True)
class WorkerJobLease:
    lease_id: UUID
    worker_id: UUID
    job: DurableJob
    lease_until: str

    def payload(self) -> dict[str, Any]:
        return {
            "lease_id": str(self.lease_id),
            "worker_id": str(self.worker_id),
            "lease_until": self.lease_until,
            "job": {
                "job_id": str(self.job.job_id),
                "objective": self.job.objective,
                "owner_id": self.job.owner_id,
                "context": self.job.context,
                "risk_level": self.job.risk_level,
                "workspace_id": str(self.job.workspace_id) if self.job.workspace_id else None,
                "retries": self.job.retries,
                "max_retries": self.job.max_retries,
                "checkpoint": self.job.checkpoint,
            },
        }


class DistributedExecutionBridge:
    """Bridges durable jobs to worker leases without allowing duplicate claims."""

    def __init__(self, jobs: JobStore, workers: WorkerCoordinator) -> None:
        self.jobs = jobs
        self.workers = workers

    @staticmethod
    def _capabilities(job: DurableJob) -> set[str]:
        raw = job.checkpoint.get("required_capabilities", []) if job.checkpoint else []
        return {str(value) for value in raw}

    def claim_next(self, worker_id: UUID) -> WorkerJobLease | None:
        worker = self.workers.get(worker_id)
        if worker is None:
            raise KeyError("unknown worker")
        required = None
        for job in self.jobs.list(limit=500):
            if job.status not in {JobStatus.QUEUED, JobStatus.RETRYING}:
                continue
            required = self._capabilities(job)
            if required and not required.issubset(set(worker.capabilities)):
                continue
            try:
                lease = self.workers.claim(worker_id, job.job_id)
            except ValueError:
                continue
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            job.error = None
            job.checkpoint = {
                **job.checkpoint,
                "distributed_lease_id": lease["lease_id"],
                "distributed_worker_id": str(worker_id),
                "distributed_claimed_at": datetime.now(timezone.utc).isoformat(),
            }
            self.jobs.save(job)
            return WorkerJobLease(UUID(lease["lease_id"]), worker_id, job, lease["lease_until"])
        return None

    def complete(self, lease_id: UUID, worker_id: UUID, result: dict[str, Any]) -> DurableJob:
        lease = self._lease_for(lease_id, worker_id)
        job = self._job_for_lease(lease)
        if job.status != JobStatus.RUNNING:
            raise ValueError("job is not running")
        job.result = result
        job.status = JobStatus.COMPLETED
        job.finished_at = datetime.now(timezone.utc)
        job.checkpoint = {**job.checkpoint, "distributed_completed": True}
        self.jobs.save(job)
        self.workers.release(lease_id)
        return job

    def fail(self, lease_id: UUID, worker_id: UUID, error: str) -> DurableJob:
        lease = self._lease_for(lease_id, worker_id)
        job = self._job_for_lease(lease)
        if job.status != JobStatus.RUNNING:
            raise ValueError("job is not running")
        if job.retries < job.max_retries:
            job.retries += 1
            job.status = JobStatus.RETRYING
            job.error = str(error)[:2000]
        else:
            job.status = JobStatus.FAILED
            job.error = str(error)[:2000]
            job.finished_at = datetime.now(timezone.utc)
        job.checkpoint = {**job.checkpoint, "distributed_last_error": job.error}
        self.jobs.save(job)
        self.workers.release(lease_id)
        return job

    def _lease_for(self, lease_id: UUID, worker_id: UUID) -> dict[str, Any]:
        # WorkerCoordinator exposes lease identity through the worker's active job;
        # ownership is checked before mutating the durable job.
        worker = self.workers.get(worker_id)
        if worker is None:
            raise KeyError("unknown worker")
        if worker.current_job_id is None:
            raise ValueError("worker has no active lease")
        with self.workers._lock, self.workers._connect() as conn:
            row = conn.execute("SELECT * FROM worker_leases WHERE lease_id=?", (str(lease_id),)).fetchone()
        if row is None:
            raise KeyError("unknown lease")
        if row["worker_id"] != str(worker_id) or row["released_at"]:
            raise ValueError("lease is not owned by worker")
        return dict(row)

    def _job_for_lease(self, lease: dict[str, Any]) -> DurableJob:
        job = self.jobs.get(UUID(lease["job_id"]))
        if job is None:
            raise KeyError("unknown job")
        return job
