from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from nexus.core.memory import MemoryRecord, MemoryStore


def test_memory_record_bounds_and_timezone_validation() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        MemoryRecord("x" * (MemoryRecord.MAX_CONTENT_CHARS + 1))
    with pytest.raises(ValueError, match="more than"):
        MemoryRecord("fact", tags=tuple(f"tag-{index}" for index in range(MemoryRecord.MAX_TAGS + 1)))
    with pytest.raises(ValueError, match="timezone"):
        MemoryRecord("fact", created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1))
    created = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="earlier"):
        MemoryRecord("fact", created_at=created, updated_at=created - timedelta(seconds=1))


def test_memory_store_filters_low_confidence_and_preserves_workspace_isolation(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    workspace_a = uuid4()
    workspace_b = uuid4()
    strong = store.remember("Use Polars for the analytics pipeline", workspace_id=workspace_a, importance=1.0)
    store.remember("Use pandas for unrelated work", workspace_id=workspace_b, importance=1.0)
    weak = store.remember("analytics note", workspace_id=workspace_a, importance=0.0)

    matches = store.recall_ranked("analytics pipeline", workspace_id=workspace_a, min_confidence=0.7)
    assert matches
    assert matches[0].record.memory_id == strong.memory_id
    assert all(match.record.workspace_id == workspace_a for match in matches)
    assert weak.memory_id not in {match.record.memory_id for match in matches}


def test_memory_store_rejects_invalid_confidence_threshold() -> None:
    store = MemoryStore()
    with pytest.raises(ValueError, match="min_confidence"):
        store.recall_ranked("analytics", min_confidence=1.1)
    with pytest.raises(ValueError, match="min_confidence"):
        store.recall("analytics", min_confidence=-0.1)


def test_memory_context_respects_confidence_filter(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    store.remember("Verified deployment uses the staging environment", importance=0.9)
    store.remember("Old deployment note", importance=0.0)
    context = store.recall_context("deployment", min_confidence=0.7)
    assert "Verified deployment" in context
    assert "Old deployment note" not in context
