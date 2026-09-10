import json
from typing import Any

from nexus.core.data_engine import DataIntelligenceEngine


def profile_dataset(csv_text: str) -> dict[str, Any]:
    """Profile a UTF-8 CSV payload without executing user-supplied code."""
    if not csv_text.strip():
        raise ValueError("CSV payload cannot be empty")

    engine = DataIntelligenceEngine()
    frame = engine.load_bytes(csv_text.encode("utf-8"), "csv")
    profile = engine.profile(frame)
    quality = engine.quality_report(frame)
    return {
        "profile": {
            "rows": profile.rows,
            "columns": profile.columns,
            "duplicate_rows": profile.duplicate_rows,
            "memory_estimate_bytes": profile.memory_estimate_bytes,
            "columns": [
                {
                    "name": column.name,
                    "dtype": column.dtype,
                    "null_count": column.null_count,
                    "null_ratio": column.null_ratio,
                    "unique_count": column.unique_count,
                }
                for column in profile.column_profiles
            ],
        },
        "quality": quality,
    }


def profile_dataset_json(csv_text: str) -> str:
    return json.dumps(profile_dataset(csv_text), default=str)
