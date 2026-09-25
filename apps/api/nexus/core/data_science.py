from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import polars as pl

from nexus.core.data_engine import DataIntelligenceEngine
from nexus.core.data_pipeline import DataPipeline
from nexus.core.datasets import DatasetRegistry
from nexus.core.dataset_workspace import DatasetWorkspace
from nexus.core.ml_engine import MLEngine


@dataclass(frozen=True)
class DataScienceReport:
    dataset_id: UUID
    profile: dict[str, Any]
    quality: dict[str, Any]
    cleaning_plan: list[dict[str, Any]]
    eda: dict[str, Any]
    correlations: list[dict[str, Any]]
    problem: dict[str, Any]
    recommendations: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": str(self.dataset_id),
            "profile": self.profile,
            "quality": self.quality,
            "cleaning_plan": self.cleaning_plan,
            "eda": self.eda,
            "correlations": self.correlations,
            "problem": self.problem,
            "recommendations": self.recommendations,
        }


class DataScienceService:
    """Dataset-scoped data-science planning and conservative baseline execution."""

    def __init__(self, workspace: DatasetWorkspace, registry: DatasetRegistry | None = None) -> None:
        self.workspace = workspace
        self.registry = registry or workspace.registry
        self.engine = DataIntelligenceEngine()
        self.pipeline = DataPipeline()
        self.ml = MLEngine()

    def _frame(self, dataset_id: UUID) -> pl.DataFrame:
        try:
            return self.workspace.load(dataset_id)
        except KeyError as exc:
            raise ValueError(f"Unknown dataset: {dataset_id}") from exc

    def inspect(self, dataset_id: UUID, target: str | None = None) -> DataScienceReport:
        frame = self._frame(dataset_id)
        profile = self.engine.profile(frame)
        quality = self.engine.quality_report(frame)
        analysis = self.pipeline.analyze(frame, target=target)
        return DataScienceReport(
            dataset_id=dataset_id,
            profile={
                "rows": profile.rows,
                "columns": profile.columns,
                "duplicate_rows": profile.duplicate_rows,
                "memory_estimate_bytes": profile.memory_estimate_bytes,
                "column_profiles": [
                    {
                        "name": item.name,
                        "dtype": item.dtype,
                        "null_count": item.null_count,
                        "null_ratio": item.null_ratio,
                        "unique_count": item.unique_count,
                    }
                    for item in profile.column_profiles
                ],
            },
            quality=quality,
            cleaning_plan=analysis["cleaning_plan"],
            eda=analysis["eda"],
            correlations=analysis["correlations"],
            problem=analysis["problem"],
            recommendations=analysis["recommendations"],
        )

    def baseline(self, dataset_id: UUID, target: str) -> dict[str, Any]:
        frame = self._frame(dataset_id)
        return {"dataset_id": str(dataset_id), **self.ml.baseline(frame, target)}

    def schema(self, dataset_id: UUID) -> dict[str, Any]:
        frame = self._frame(dataset_id)
        columns = []
        for name in frame.columns:
            series = frame.get_column(name)
            columns.append({
                "name": name,
                "dtype": str(series.dtype),
                "numeric": bool(series.dtype in pl.NUMERIC_DTYPES),
                "nullable": series.null_count() > 0,
                "null_count": series.null_count(),
                "unique_count": series.n_unique(),
            })
        return {
            "dataset_id": str(dataset_id),
            "rows": frame.height,
            "columns": columns,
        }
