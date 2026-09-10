from dataclasses import dataclass
from io import BytesIO
from typing import Any

import polars as pl


SUPPORTED_FORMATS = {"csv", "parquet", "json"}


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    dtype: str
    null_count: int
    null_ratio: float
    unique_count: int


@dataclass(frozen=True)
class DataProfile:
    rows: int
    columns: int
    duplicate_rows: int
    memory_estimate_bytes: int
    column_profiles: tuple[ColumnProfile, ...]


class DataIntelligenceEngine:
    """Deterministic foundation for NEXUS data understanding.

    The engine intentionally separates ingestion, profiling, and quality
    analysis so later agents can plan cleaning, EDA, statistics, and ML work
    from structured evidence rather than guessing from raw files.
    """

    def load_bytes(self, data: bytes, file_format: str) -> pl.DataFrame:
        normalized = file_format.lower().lstrip(".")
        if normalized not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format '{file_format}'. Supported formats: {sorted(SUPPORTED_FORMATS)}"
            )
        if not data:
            raise ValueError("Dataset cannot be empty")

        buffer = BytesIO(data)
        if normalized == "csv":
            return pl.read_csv(buffer)
        if normalized == "parquet":
            return pl.read_parquet(buffer)
        return pl.read_json(buffer)

    def profile(self, frame: pl.DataFrame) -> DataProfile:
        if frame is None:
            raise ValueError("DataFrame cannot be None")

        row_count = frame.height
        profiles: list[ColumnProfile] = []
        for column in frame.columns:
            series = frame.get_column(column)
            null_count = series.null_count()
            profiles.append(
                ColumnProfile(
                    name=column,
                    dtype=str(series.dtype),
                    null_count=null_count,
                    null_ratio=(null_count / row_count) if row_count else 0.0,
                    unique_count=series.n_unique(),
                )
            )

        duplicate_rows = row_count - frame.unique().height
        memory_estimate = sum(
            int(series.estimated_size()) for series in frame.get_columns()
        )
        return DataProfile(
            rows=row_count,
            columns=frame.width,
            duplicate_rows=duplicate_rows,
            memory_estimate_bytes=memory_estimate,
            column_profiles=tuple(profiles),
        )

    def quality_report(self, frame: pl.DataFrame) -> dict[str, Any]:
        profile = self.profile(frame)
        null_columns = [
            {
                "column": column.name,
                "null_count": column.null_count,
                "null_ratio": column.null_ratio,
            }
            for column in profile.column_profiles
            if column.null_count
        ]
        constant_columns = [
            column.name
            for column in profile.column_profiles
            if column.unique_count <= 1 and profile.rows > 0
        ]
        return {
            "rows": profile.rows,
            "columns": profile.columns,
            "duplicate_rows": profile.duplicate_rows,
            "null_columns": null_columns,
            "constant_columns": constant_columns,
            "quality_flags": {
                "has_missing_values": bool(null_columns),
                "has_duplicates": profile.duplicate_rows > 0,
                "has_constant_columns": bool(constant_columns),
            },
        }
