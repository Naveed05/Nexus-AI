from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import sqlite3
from threading import RLock
from uuid import UUID, uuid4


class JobStatus(str, Enum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ExecutionJob:
    job_id: UUID
    run_id: UUID
    status: JobStatus
    attempts: int
    worker_id: str | None
    created_at: datetime
    updated_at: datetime


class ExecutionQueue:
    """SQLite-backed job boundary suitable for a future Redis/worker adapter."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = RLock()
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS execution_jobs (
                job_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, status TEXT NOT NULL,
                attempts INTEGER NOT NULL, worker_id TEXT, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
            conn.commit()

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def enqueue(self, run_id: UUID) -> ExecutionJob:
        now = datetime.now(timezone.utc)
        job = ExecutionJob(uuid4(), run_id, JobStatus.QUEUED, 0, None, now, now)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO execution_jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(job.job_id), str(job.run_id), job.status.value, 0, None, now.isoformat(), now.isoformat()),
            )
            conn.commit()
        return job

    def claim(self, worker_id: str) -> ExecutionJob | None:
        if not worker_id.strip():
            raise ValueError("worker_id cannot be empty")
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM execution_jobs WHERE status = ? ORDER BY created_at, job_id LIMIT 1",
                (JobStatus.QUEUED.value,),
            ).fetchone()
            if row is None:
                return None
            now = self._now()
            conn.execute(
                "UPDATE execution_jobs SET status = ?, attempts = attempts + 1, worker_id = ?, updated_at = ? WHERE job_id = ? AND status = ?",
                (JobStatus.CLAIMED.value, worker_id, now, row["job_id"], JobStatus.QUEUED.value),
            )
            conn.commit()
            return self.get(UUID(row["job_id"]))

    def complete(self, job_id: UUID, *, failed: bool = False) -> ExecutionJob:
        status = JobStatus.FAILED if failed else JobStatus.COMPLETED
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE execution_jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                (status.value, self._now(), str(job_id)),
            )
            conn.commit()
        return self.get(job_id)

    def get(self, job_id: UUID) -> ExecutionJob:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM execution_jobs WHERE job_id = ?", (str(job_id),)).fetchone()
        if row is None:
            raise KeyError(f"Unknown execution job: {job_id}")
        return ExecutionJob(
            UUID(row["job_id"]), UUID(row["run_id"]), JobStatus(row["status"]),
            row["attempts"], row["worker_id"], datetime.fromisoformat(row["created_at"]),
            datetime.fromisoformat(row["updated_at"]),
        )
