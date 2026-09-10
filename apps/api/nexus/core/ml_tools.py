from typing import Any

from nexus.core.data_engine import DataIntelligenceEngine
from nexus.core.ml_engine import MLEngine


def baseline_ml(csv_text: str, target: str) -> dict[str, Any]:
    """Train and evaluate a conservative baseline model for an explicit target."""
    if not csv_text.strip():
        raise ValueError("CSV payload cannot be empty")
    frame = DataIntelligenceEngine().load_bytes(csv_text.encode("utf-8"), "csv")
    return MLEngine().baseline(frame, target)
