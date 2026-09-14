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

    context = store.recall_context("deterministic test", workspace_id=workspace, max_chars=80)
    assert context.startswith("RECALLED MEMORY (workspace-scoped):")
    assert len(context) <= 80

    with pytest.raises(KeyError):
        store.forget(record.memory_id, workspace_id=other_workspace)
    assert store.forget(record.memory_id, workspace_id=workspace) == record
    assert store.list(workspace_id=workspace) == ()


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
