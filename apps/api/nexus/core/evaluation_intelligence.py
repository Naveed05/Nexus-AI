"""Production evaluation intelligence: durable runs, telemetry, regressions, and trend analysis."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus.core.evaluation import EvaluationReport


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class EvaluationRun:
    run_id: str
    suite_name: str
    suite_version: str
    report: dict[str, Any]
    metadata: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class EvaluationTelemetry:
    event_id: str
    run_id: str | None
    component_type: str
    component_id: str
    success: bool
    latency_ms: float
    tokens: int
    cost_usd: float
    quality_score: float | None
    metadata: dict[str, Any]
    created_at: str


class EvaluationIntelligenceStore:
    """SQLite-backed evaluation history and component telemetry."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS evaluation_runs (
                    run_id TEXT PRIMARY KEY,
                    suite_name TEXT NOT NULL,
                    suite_version TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evaluation_telemetry (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    component_type TEXT NOT NULL,
                    component_id TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    tokens INTEGER NOT NULL,
                    cost_usd REAL NOT NULL,
                    quality_score REAL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_eval_runs_suite
                    ON evaluation_runs(suite_name, suite_version, created_at);
                CREATE INDEX IF NOT EXISTS idx_eval_telemetry_component
                    ON evaluation_telemetry(component_type, component_id, created_at);
                """
            )

    def save_run(self, suite_name: str, suite_version: str, report: EvaluationReport | dict[str, Any],
                 metadata: dict[str, Any] | None = None, run_id: str | None = None) -> EvaluationRun:
        payload = report.as_dict() if isinstance(report, EvaluationReport) else dict(report)
        rid = run_id or str(uuid.uuid4())
        created = _now()
        meta = dict(metadata or {})
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT INTO evaluation_runs(run_id,suite_name,suite_version,report_json,metadata_json,created_at) VALUES(?,?,?,?,?,?)",
                (rid, suite_name, suite_version, json.dumps(payload, sort_keys=True),
                 json.dumps(meta, sort_keys=True), created),
            )
        return EvaluationRun(rid, suite_name, suite_version, payload, meta, created)

    def get_run(self, run_id: str) -> EvaluationRun | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT run_id,suite_name,suite_version,report_json,metadata_json,created_at FROM evaluation_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if not row:
            return None
        return EvaluationRun(row[0], row[1], row[2], json.loads(row[3]), json.loads(row[4]), row[5])

    def list_runs(self, suite_name: str | None = None, limit: int = 100) -> list[EvaluationRun]:
        limit = max(1, min(int(limit), 500))
        query = "SELECT run_id,suite_name,suite_version,report_json,metadata_json,created_at FROM evaluation_runs"
        params: tuple[Any, ...] = ()
        if suite_name:
            query += " WHERE suite_name=?"
            params = (suite_name,)
        query += " ORDER BY created_at DESC LIMIT ?"
        params += (limit,)
        with sqlite3.connect(self.path) as db:
            rows = db.execute(query, params).fetchall()
        return [EvaluationRun(r[0], r[1], r[2], json.loads(r[3]), json.loads(r[4]), r[5]) for r in rows]

    def save_telemetry(self, event: EvaluationTelemetry) -> None:
        if event.latency_ms < 0 or event.tokens < 0 or event.cost_usd < 0:
            raise ValueError("telemetry numeric values cannot be negative")
        if not event.component_type.strip() or not event.component_id.strip():
            raise ValueError("telemetry component identity cannot be empty")
        with sqlite3.connect(self.path) as db:
            db.execute(
                """INSERT INTO evaluation_telemetry
                (event_id,run_id,component_type,component_id,success,latency_ms,tokens,cost_usd,quality_score,metadata_json,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (event.event_id, event.run_id, event.component_type, event.component_id,
                 int(event.success), event.latency_ms, event.tokens, event.cost_usd,
                 event.quality_score, json.dumps(event.metadata, sort_keys=True), event.created_at),
            )

    def component_metrics(self, component_type: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        query = """SELECT component_type,component_id,COUNT(*),SUM(success),AVG(latency_ms),
                   SUM(tokens),SUM(cost_usd),AVG(quality_score)
                   FROM evaluation_telemetry"""
        params: tuple[Any, ...] = ()
        if component_type:
            query += " WHERE component_type=?"
            params = (component_type,)
        query += " GROUP BY component_type,component_id ORDER BY component_type,component_id LIMIT ?"
        params += (limit,)
        with sqlite3.connect(self.path) as db:
            rows = db.execute(query, params).fetchall()
        return [
            {
                "component_type": r[0], "component_id": r[1], "events": r[2],
                "successes": r[3], "success_rate": round(r[3] / r[2], 3),
                "average_latency_ms": round(r[4], 3), "total_tokens": r[5],
                "total_cost_usd": round(r[6], 6),
                "average_quality_score": round(r[7], 3) if r[7] is not None else None,
            }
            for r in rows
        ]


def compare_reports(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Compare persisted reports without deserializing arbitrary Python objects."""
    keys = ("pass_rate", "average_check_score", "average_grounding_score")
    deltas = {key: round(float(current.get(key, 0)) - float(baseline.get(key, 0)), 3) for key in keys}
    baseline_cases = {item["case_id"]: item for item in baseline.get("scores", []) if isinstance(item, dict) and "case_id" in item}
    current_cases = {item["case_id"]: item for item in current.get("scores", []) if isinstance(item, dict) and "case_id" in item}
    failed = sorted(k for k, v in baseline_cases.items() if v.get("passed") and not current_cases.get(k, {}).get("passed"))
    recovered = sorted(k for k, v in baseline_cases.items() if not v.get("passed") and current_cases.get(k, {}).get("passed"))
    return {
        "deltas": deltas,
        "regressed": any(value < 0 for value in deltas.values()),
        "failed_case_ids": failed,
        "recovered_case_ids": recovered,
    }


def trend_summary(runs: list[EvaluationRun]) -> dict[str, Any]:
    ordered = list(reversed(runs))
    points = [
        {
            "run_id": item.run_id,
            "created_at": item.created_at,
            "pass_rate": item.report.get("pass_rate", 0),
            "check_score": item.report.get("average_check_score", 0),
            "grounding_score": item.report.get("average_grounding_score", 0),
        }
        for item in ordered
    ]
    if len(points) < 2:
        return {"points": points, "direction": "insufficient-data", "drift": False}
    latest, previous = points[-1], points[-2]
    changes = {k: round(latest[k] - previous[k], 3) for k in ("pass_rate", "check_score", "grounding_score")}
    return {
        "points": points,
        "direction": "improving" if sum(changes.values()) > 0 else "declining" if sum(changes.values()) < 0 else "stable",
        "drift": any(abs(v) >= 0.1 for v in changes.values()),
        "latest_deltas": changes,
    }


def telemetry_event(
    component_type: str,
    component_id: str,
    *,
    run_id: str | None = None,
    success: bool = True,
    latency_ms: float = 0,
    tokens: int = 0,
    cost_usd: float = 0,
    quality_score: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> EvaluationTelemetry:
    return EvaluationTelemetry(
        event_id=str(uuid.uuid4()), run_id=run_id, component_type=component_type,
        component_id=component_id, success=success, latency_ms=latency_ms,
        tokens=tokens, cost_usd=cost_usd, quality_score=quality_score,
        metadata=dict(metadata or {}), created_at=_now(),
    )
