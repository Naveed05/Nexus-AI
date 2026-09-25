from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from .data_engine import DataIntelligenceEngine
from .data_pipeline import DataPipeline
from .dataset_workspace import DatasetWorkspace
from .ml_engine import MLEngine


class DataScienceIntelligence:
    """Workspace-scoped data-science service with durable analysis snapshots."""

    def __init__(self, datasets: DatasetWorkspace, storage_path: str | Path) -> None:
        self.datasets = datasets
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.storage_path, check_same_thread=False)
        self._connection.execute("""CREATE TABLE IF NOT EXISTS analyses (
            analysis_id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            analysis_type TEXT NOT NULL,
            target TEXT,
            result TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        self._connection.commit()
        self.engine = DataIntelligenceEngine()
        self.pipeline = DataPipeline()
        self.ml = MLEngine()

    def _save(self, dataset_id: UUID, analysis_type: str, result: dict[str, Any], target: str | None = None) -> dict[str, Any]:
        analysis_id = uuid4()
        created_at = datetime.now(timezone.utc).isoformat()
        self._connection.execute(
            "INSERT INTO analyses VALUES (?,?,?,?,?,?)",
            (str(analysis_id), str(dataset_id), analysis_type, target, json.dumps(result, default=str), created_at),
        )
        self._connection.commit()
        return {"analysis_id": str(analysis_id), "dataset_id": str(dataset_id), "analysis_type": analysis_type, "target": target, "created_at": created_at, "result": result}

    def profile(self, dataset_id: UUID) -> dict[str, Any]:
        frame = self.datasets.load(dataset_id)
        profile = self.engine.profile(frame)
        result = {
            "rows": profile.rows,
            "columns": profile.columns,
            "duplicate_rows": profile.duplicate_rows,
            "memory_estimate_bytes": profile.memory_estimate_bytes,
            "column_profiles": [vars(column) for column in profile.column_profiles],
            "quality": self.engine.quality_report(frame),
        }
        return self._save(dataset_id, "profile", result)

    def analyze(self, dataset_id: UUID, target: str | None = None) -> dict[str, Any]:
        frame = self.datasets.load(dataset_id)
        return self._save(dataset_id, "analysis", self.pipeline.analyze(frame, target=target), target)

    def baseline(self, dataset_id: UUID, target: str) -> dict[str, Any]:
        frame = self.datasets.load(dataset_id)
        return self._save(dataset_id, "baseline_ml", self.ml.baseline(frame, target), target)

    def history(self, dataset_id: UUID, limit: int = 50) -> list[dict[str, Any]]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        rows = self._connection.execute(
            "SELECT analysis_id,dataset_id,analysis_type,target,result,created_at FROM analyses WHERE dataset_id=? ORDER BY created_at DESC LIMIT ?",
            (str(dataset_id), limit),
        ).fetchall()
        return [{
            "analysis_id": row[0], "dataset_id": row[1], "analysis_type": row[2], "target": row[3],
            "result": json.loads(row[4]), "created_at": row[5]
        } for row in rows]
