"""Phase 63: durable operational reliability and recovery control plane."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ReliabilityRecord:
    record_id: int
    action: str
    status: str
    details: dict[str, Any]
    created_at: str


class ReliabilityStore:
    """Small durable journal for recovery actions and operational snapshots."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS reliability_records (
                    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_reliability_created
                    ON reliability_records(created_at);
                """
            )

    def record(self, action: str, status: str, details: dict[str, Any]) -> ReliabilityRecord:
        created = _now()
        with sqlite3.connect(self.path) as db:
            cur = db.execute(
                "INSERT INTO reliability_records(action,status,details_json,created_at) VALUES(?,?,?,?)",
                (action, status, json.dumps(details, sort_keys=True, default=str), created),
            )
            record_id = int(cur.lastrowid)
        return ReliabilityRecord(record_id, action, status, dict(details), created)

    def list(self, limit: int = 50) -> list[ReliabilityRecord]:
        limit = max(1, min(int(limit), 500))
        with sqlite3.connect(self.path) as db:
            rows = db.execute(
                "SELECT record_id,action,status,details_json,created_at "
                "FROM reliability_records ORDER BY record_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            ReliabilityRecord(int(row[0]), row[1], row[2], json.loads(row[3] or "{}"), row[4])
            for row in rows
        ]


class ReliabilityControlPlane:
    """Coordinates safe stale-worker/job recovery and records the outcome."""

    def __init__(self, store: ReliabilityStore) -> None:
        self.store = store

    def snapshot(self, *, job_manager: Any, worker_coordinator: Any, event_store: Any) -> dict[str, Any]:
        jobs = job_manager.stats()
        workers = worker_coordinator.metrics()
        events = event_store.summary()
        status = "healthy"
        if jobs.get("failed", 0) > 0 or workers.get("offline_count", 0) > 0:
            status = "attention"
        return {
            "status": status,
            "jobs": jobs,
            "workers": workers,
            "events": events,
            "checked_at": _now(),
        }

    def reconcile(self, *, distributed_bridge: Any, worker_coordinator: Any, job_manager: Any, event_store: Any) -> dict[str, Any]:
        """Recover stale leases/jobs, then persist an auditable reconciliation record."""
        try:
            recovered_leases = worker_coordinator.recover_stale()
            recovered_jobs = distributed_bridge.recover_stale_jobs()
            snapshot = self.snapshot(
                job_manager=job_manager,
                worker_coordinator=worker_coordinator,
                event_store=event_store,
            )
            record = self.store.record(
                "reconcile",
                "completed",
                {
                    "recovered_leases": int(recovered_leases or 0),
                    "recovered_jobs": int(recovered_jobs or 0),
                    "snapshot": snapshot,
                },
            )
            return {
                "record_id": record.record_id,
                "recovered_leases": int(recovered_leases or 0),
                "recovered_jobs": int(recovered_jobs or 0),
                "snapshot": snapshot,
            }
        except Exception as exc:
            self.store.record("reconcile", "failed", {"error": str(exc)})
            raise
