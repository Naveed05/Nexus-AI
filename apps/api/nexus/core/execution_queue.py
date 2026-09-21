from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import sqlite3
from threading import RLock
from uuid import UUID, uuid4


class JobStatus(str, Enum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


@dataclass(frozen=True)
class ExecutionJob:
    job_id: UUID
    run_id: UUID
    status: JobStatus
    attempts: int
    worker_id: str | None
    created_at: datetime
    updated_at: datetime
    lease_until: datetime | None = None


class ExecutionQueue:
    """Durable queue boundary with leases, retry limits, and dead-letter state."""

    def __init__(self, path: str, *, lease_seconds: int = 60, max_attempts: int = 3) -> None:
        if lease_seconds < 1 or max_attempts < 1:
            raise ValueError("lease_seconds and max_attempts must be at least 1")
        self.path = path
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self._lock = RLock()
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS execution_jobs (
                job_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, status TEXT NOT NULL,
                attempts INTEGER NOT NULL, worker_id TEXT, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, lease_until TEXT
            )""")
            self._ensure_column(conn, "lease_until", "TEXT")
            conn.commit()

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, name: str, definition: str) -> None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(execution_jobs)")}
        if name not in columns:
            conn.execute(f"ALTER TABLE execution_jobs ADD COLUMN {name} {definition}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def enqueue(self, run_id: UUID) -> ExecutionJob:
        now = self._now()
        job = ExecutionJob(uuid4(), run_id, JobStatus.QUEUED, 0, None, now, now, None)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO execution_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(job.job_id), str(job.run_id), job.status.value, 0, None,
                 now.isoformat(), now.isoformat(), None),
            )
            conn.commit()
        return job

    def _requeue_expired(self, conn: sqlite3.Connection, now: datetime) -> None:
        conn.execute(
            "UPDATE execution_jobs SET status = ?, worker_id = NULL, lease_until = NULL, updated_at = ? "
            "WHERE status = ? AND lease_until IS NOT NULL AND lease_until <= ?",
            (JobStatus.QUEUED.value, now.isoformat(), JobStatus.CLAIMED.value, now.isoformat()),
        )

    def claim(self, worker_id: str) -> ExecutionJob | None:
        if not worker_id.strip():
            raise ValueError("worker_id cannot be empty")
        with self._lock, self._connect() as conn:
            now = self._now()
            self._requeue_expired(conn, now)
            row = conn.execute(
                "SELECT * FROM execution_jobs WHERE status = ? AND attempts < ? ORDER BY created_at, job_id LIMIT 1",
                (JobStatus.QUEUED.value, self.max_attempts),
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            lease_until = now + timedelta(seconds=self.lease_seconds)
            conn.execute(
                "UPDATE execution_jobs SET status = ?, attempts = attempts + 1, worker_id = ?, "
                "lease_until = ?, updated_at = ? WHERE job_id = ? AND status = ?",
                (JobStatus.CLAIMED.value, worker_id, lease_until.isoformat(), now.isoformat(),
                 row["job_id"], JobStatus.QUEUED.value),
            )
            conn.commit()
            return self.get(UUID(row["job_id"]))

    def complete(self, job_id: UUID, *, worker_id: str | None = None, failed: bool = False) -> ExecutionJob:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM execution_jobs WHERE job_id = ?", (str(job_id),)).fetchone()
            if row is None:
                raise KeyError(f"Unknown execution job: {job_id}")
            if worker_id and row["worker_id"] != worker_id:
                raise ValueError("worker does not own the job lease")
            if row["status"] != JobStatus.CLAIMED.value:
                raise ValueError("only claimed jobs can be completed")
            status = JobStatus.DEAD_LETTER if failed and int(row["attempts"]) >= self.max_attempts else (
                JobStatus.QUEUED if failed else JobStatus.COMPLETED
            )
            conn.execute(
                "UPDATE execution_jobs SET status = ?, worker_id = ?, lease_until = NULL, updated_at = ? WHERE job_id = ?",
                (status.value, None if status != JobStatus.CLAIMED else row["worker_id"],
                 self._now().isoformat(), str(job_id)),
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
            int(row["attempts"]), row["worker_id"], datetime.fromisoformat(row["created_at"]),
            datetime.fromisoformat(row["updated_at"]),
            datetime.fromisoformat(row["lease_until"]) if row["lease_until"] else None,
        )

    def stats(self) -> dict[str, int]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS count FROM execution_jobs GROUP BY status").fetchall()
        return {row["status"]: int(row["count"]) for row in rows}
