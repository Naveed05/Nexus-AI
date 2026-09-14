from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from nexus.core.memory import MemoryStore


def test_memory_store_isolates_workspaces_and_ranks_relevant_records() -> None:
    store = MemoryStore()
    workspace = uuid4()
    other_workspace = uuid4()

    important = store.remember("User prefers concise Python examples", workspace_id=workspace, tags=("Preference",), importance=0.9)
    store.remember("Unrelated deployment note", workspace_id=workspace, importance=0.2)
    store.remember("User prefers concise Java examples", workspace_id=other_workspace, importance=1.0)

    recalled = store.recall("concise Python", workspace_id=workspace)

    assert recalled == (important,)
    assert store.recall("Java", workspace_id=workspace) == ()


def test_memory_context_is_bounded_and_forget_is_workspace_scoped() -> None:
    store = MemoryStore()
    workspace = uuid4()
    other_workspace = uuid4()
    record = store.remember("Use the repository's deterministic test suite", workspace_id=workspace, tags=("testing",))

    context = store.recall_context("deterministic test", workspace_id=workspace, max_chars=300)
    assert context.startswith("RECALLED MEMORY (workspace-scoped):")
    assert "confidence=" in context
    assert "relevance=" in context
    assert len(context) <= 300

    with pytest.raises(KeyError):
        store.forget(record.memory_id, workspace_id=other_workspace)
    assert store.forget(record.memory_id, workspace_id=workspace) == record
    assert store.list(workspace_id=workspace) == ()


def test_memory_recall_exposes_deterministic_confidence() -> None:
    store = MemoryStore()
    workspace = uuid4()
    record = store.remember("Verified Python testing workflow", workspace_id=workspace, importance=0.5)

    matches = store.recall_ranked("Python testing", workspace_id=workspace)

    assert len(matches) == 1
    assert matches[0].record == record
    assert matches[0].relevance == 1.0
    assert matches[0].confidence == 0.9


def test_memory_deduplicates_and_reinforces_existing_record() -> None:
    store = MemoryStore()
    workspace = uuid4()
    record = store.remember("Use pytest for API regression checks", workspace_id=workspace, tags=("Testing",), importance=0.4)
    duplicate = store.remember("Use pytest for API regression checks", workspace_id=workspace, tags=("testing",), importance=0.8)

    assert duplicate.memory_id == record.memory_id
    assert duplicate.importance == 0.8
    assert len(store.list(workspace_id=workspace)) == 1

    reinforced = store.reinforce(record.memory_id, workspace_id=workspace, amount=0.3)
    assert reinforced.importance == 1.0
    assert reinforced.updated_at >= duplicate.updated_at

    with pytest.raises(ValueError):
        store.reinforce(record.memory_id, workspace_id=workspace, amount=-0.1)


def test_memory_sqlite_store_is_safe_for_concurrent_api_requests(tmp_path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    workspace = uuid4()

    def write_memory(index: int) -> None:
        store.remember(f"Concurrent memory {index}", workspace_id=workspace, tags=("concurrent",), importance=0.5)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write_memory, range(24)))

    records = store.list(workspace_id=workspace)
    assert len(records) == 24
    assert {record.content for record in records} == {f"Concurrent memory {index}" for index in range(24)}


def test_memory_validation_rejects_invalid_inputs() -> None:
    store = MemoryStore()

    with pytest.raises(ValueError):
        store.remember("   ")
    with pytest.raises(ValueError):
        store.remember("fact", importance=1.1)
    with pytest.raises(ValueError):
        store.recall("   ")
    with pytest.raises(ValueError):
        store.recall("fact", top_k=0)
    with pytest.raises(ValueError):
        store.recall_context("fact", max_chars=0)
