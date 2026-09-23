from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
import sqlite3
from threading import Event, RLock, Thread
import time
from typing import Any, Callable
from uuid import UUID, uuid4


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
}


@dataclass
class DurableJob:
    job_id: UUID
    objective: str
    context: str | None = None
    risk_level: str = "low"
    workspace_id: UUID | None = None
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = None  # type: ignore[assignment]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    retries: int = 0
    max_retries: int = 3
    run_id: UUID | None = None
    artifact_id: UUID | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    checkpoint: dict[str, Any] = None  # type: ignore[assignment]
    version: int = 0

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.checkpoint is None:
            self.checkpoint = {}
        if not self.objective.strip():
            raise ValueError("objective cannot be empty")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.retries < 0:
            raise ValueError("retries cannot be negative")

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_JOB_STATES


class JobStore:
    """SQLite persistence for durable workflow jobs."""

    def __init__(self, path: str = ".nexus/jobs.sqlite3") -> None:
        self.path = path
        self._lock = RLock()
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    context TEXT,
                    risk_level TEXT NOT NULL,
                    workspace_id TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    retries INTEGER NOT NULL,
                    max_retries INTEGER NOT NULL,
                    run_id TEXT,
                    artifact_id TEXT,
                    error TEXT,
                    result TEXT NOT NULL,
                    checkpoint TEXT NOT NULL,
                    version INTEGER NOT NULL
                )"""
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _dt(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value else None

    def save(self, job: DurableJob) -> DurableJob:
        with self._lock, self._connect() as conn:
            job.version += 1
            conn.execute(
                """INSERT OR REPLACE INTO jobs
                (job_id, objective, owner_id, context, risk_level, workspace_id, status,
                 created_at, started_at, finished_at, retries, max_retries, run_id,
                 artifact_id, error, result, checkpoint, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(job.job_id), job.objective, job.owner_id, job.context, job.risk_level,
                    str(job.workspace_id) if job.workspace_id else None,
                    job.status.value, self._dt(job.created_at), self._dt(job.started_at),
                    self._dt(job.finished_at), job.retries, job.max_retries,
                    str(job.run_id) if job.run_id else None,
                    str(job.artifact_id) if job.artifact_id else None,
                    job.error, json.dumps(job.result or {}, default=str),
                    json.dumps(job.checkpoint or {}, default=str), job.version,
                ),
            )
            conn.commit()
        return job

    def get(self, job_id: UUID) -> DurableJob | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (str(job_id),)).fetchone()
        return self._from_row(row) if row else None

    def list(self, *, limit: int = 100) -> list[DurableJob]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def recover_interrupted(self) -> int:
        """Move orphaned running jobs back to the durable queue on restart."""
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "UPDATE jobs SET status = ?, error = ?, started_at = NULL "
                "WHERE status IN (?, ?)",
                (
                    JobStatus.QUEUED.value,
                    "Recovered after worker restart",
                    JobStatus.RUNNING.value,
                    JobStatus.RETRYING.value,
                ),
            )
            conn.commit()
            return cursor.rowcount

    @staticmethod
    def _from_row(row: sqlite3.Row) -> DurableJob:
        return DurableJob(
            job_id=UUID(row["job_id"]),
            objective=row["objective"],
            context=row["context"],
            risk_level=row["risk_level"],
            workspace_id=UUID(row["workspace_id"]) if row["workspace_id"] else None,
            status=JobStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=JobStore._parse_dt(row["started_at"]),
            finished_at=JobStore._parse_dt(row["finished_at"]),
            retries=row["retries"],
            max_retries=row["max_retries"],
            run_id=UUID(row["run_id"]) if row["run_id"] else None,
            artifact_id=UUID(row["artifact_id"]) if row["artifact_id"] else None,
            error=row["error"],
            result=json.loads(row["result"] or "{}"),
            checkpoint=json.loads(row["checkpoint"] or "{}"),
            version=row["version"],
        )


class DurableJobManager:
    """Bounded background worker with durable state and explicit recovery controls."""

    def __init__(
        self,
        store: JobStore,
        executor: Callable[[DurableJob], dict[str, Any]],
        *,
        auto_start: bool = True,
        poll_interval: float = 0.25,
    ) -> None:
        self.store = store
        self.executor = executor
        self.poll_interval = max(0.05, poll_interval)
        self._lock = RLock()
        self._stop = Event()
        self._wake = Event()
        self._active: set[UUID] = set()
        self.store.recover_interrupted()
        self._thread: Thread | None = None
        if auto_start:
            self.start()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = Thread(target=self._worker, name="nexus-job-worker", daemon=True)
            self._thread.start()

    def stop(self, *, timeout: float = 2.0) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread:
            thread.join(timeout=timeout)

    def submit(
        self,
        objective: str,
        *,
        context: str | None = None,
        risk_level: str = "low",
        workspace_id: UUID | None = None,
        max_retries: int = 3,
    ) -> DurableJob:
        job = DurableJob(
            job_id=uuid4(),
            objective=objective,
            context=context,
            risk_level=risk_level,
            workspace_id=workspace_id,
            max_retries=max_retries,
        )
        self.store.save(job)
        self._wake.set()
        return job

    def get(self, job_id: UUID) -> DurableJob:
        job = self.store.get(job_id)
        if job is None:
            raise KeyError(f"Unknown job: {job_id}")
        return job

    def list(self, *, limit: int = 100) -> list[DurableJob]:
        return self.store.list(limit=limit)

    def cancel(self, job_id: UUID) -> DurableJob:
        job = self.get(job_id)
        if job.terminal:
            return job
        job.status = JobStatus.CANCELLED
        job.error = "Cancelled by operator"
        job.finished_at = datetime.now(timezone.utc)
        self.store.save(job)
        return job

    def pause(self, job_id: UUID) -> DurableJob:
        job = self.get(job_id)
        if job.terminal:
            return job
        job.status = JobStatus.PAUSED
        job.checkpoint = {**job.checkpoint, "paused_at": datetime.now(timezone.utc).isoformat()}
        self.store.save(job)
        return job

    def resume(self, job_id: UUID) -> DurableJob:
        job = self.get(job_id)
        if job.status != JobStatus.PAUSED:
            raise ValueError("only paused jobs can be resumed")
        job.status = JobStatus.QUEUED
        job.error = None
        job.finished_at = None
        self.store.save(job)
        self._wake.set()
        return job

    def retry(self, job_id: UUID) -> DurableJob:
        job = self.get(job_id)
        if job.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
            raise ValueError("only failed or cancelled jobs can be retried")
        if job.retries >= job.max_retries:
            raise ValueError("job retry budget exhausted")
        job.retries += 1
        job.status = JobStatus.RETRYING
        job.error = None
        job.finished_at = None
        self.store.save(job)
        self._wake.set()
        return job

    def stats(self) -> dict[str, int]:
        jobs = self.store.list(limit=500)
        counts = {status.value: 0 for status in JobStatus}
        for job in jobs:
            counts[job.status.value] += 1
        counts["total"] = len(jobs)
        counts["active_workers"] = len(self._active)
        return counts

    def _next_job(self) -> DurableJob | None:
        for job in self.store.list(limit=500):
            if job.status in {JobStatus.QUEUED, JobStatus.RETRYING}:
                return job
        return None

    def _worker(self) -> None:
        while not self._stop.is_set():
            job = self._next_job()
            if job is None:
                self._wake.wait(self.poll_interval)
                self._wake.clear()
                continue
            with self._lock:
                self._active.add(job.job_id)
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            job.error = None
            self.store.save(job)
            try:
                result = self.executor(job)
                current = self.store.get(job.job_id)
                if current is None:
                    continue
                if current.status == JobStatus.CANCELLED:
                    continue
                if current.status == JobStatus.PAUSED:
                    continue
                current.result = result
                current.status = JobStatus.COMPLETED
                current.finished_at = datetime.now(timezone.utc)
                current.checkpoint = {**current.checkpoint, "completed": True}
                self.store.save(current)
            except Exception as exc:
                current = self.store.get(job.job_id) or job
                if current.status in {JobStatus.CANCELLED, JobStatus.PAUSED}:
                    self.store.save(current)
                elif current.retries < current.max_retries:
                    current.retries += 1
                    current.status = JobStatus.RETRYING
                    current.error = str(exc)
                    current.checkpoint = {**current.checkpoint, "last_error": str(exc)}
                    self.store.save(current)
                    time.sleep(min(2 ** min(current.retries, 5), 16))
                else:
                    current.status = JobStatus.FAILED
                    current.error = str(exc)
                    current.finished_at = datetime.now(timezone.utc)
                    current.checkpoint = {**current.checkpoint, "failed": True}
                    self.store.save(current)
            finally:
                with self._lock:
                    self._active.discard(job.job_id)


def job_payload(job: DurableJob) -> dict[str, Any]:
    return {
        "job_id": str(job.job_id),
        "objective": job.objective,
        "context": job.context,
        "risk_level": job.risk_level,
        "workspace_id": str(job.workspace_id) if job.workspace_id else None,
        "status": job.status.value,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "retries": job.retries,
        "max_retries": job.max_retries,
        "run_id": str(job.run_id) if job.run_id else None,
        "artifact_id": str(job.artifact_id) if job.artifact_id else None,
        "error": job.error,
        "result": job.result or {},
        "checkpoint": job.checkpoint or {},
        "version": job.version,
    }
