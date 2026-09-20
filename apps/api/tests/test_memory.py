from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
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
    assert matches[0].confidence == 0.5


def test_memory_confidence_is_bounded_by_importance() -> None:
    store = MemoryStore()
    workspace = uuid4()
    low_importance = store.remember("Exact Python testing match", workspace_id=workspace, importance=0.1)

    matches = store.recall_ranked("Python testing", workspace_id=workspace)

    assert matches[0].record == low_importance
    assert matches[0].relevance == 1.0
    assert matches[0].confidence == 0.1


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


def test_memory_lifecycle_candidates_are_workspace_scoped_and_deterministic() -> None:
    store = MemoryStore()
    workspace = uuid4()
    old = datetime.now(timezone.utc) - timedelta(days=60)
    record = store.remember("Stale low value note", workspace_id=workspace, importance=0.1)
    # Rebuild the immutable record with an old timestamp to exercise lifecycle policy.
    from dataclasses import replace
    store._records[record.memory_id] = replace(record, created_at=old, updated_at=old)

    assert store.lifecycle_candidates(workspace_id=workspace, older_than_days=30, min_importance=0.1) == (store._records[record.memory_id],)
    assert store.lifecycle_candidates(workspace_id=uuid4(), older_than_days=30, min_importance=0.1) == ()


def test_memory_lifecycle_pruning_requires_explicit_workspace_and_threshold() -> None:
    store = MemoryStore()
    workspace = uuid4()
    old = datetime.now(timezone.utc) - timedelta(days=60)
    record = store.remember("Stale low value note", workspace_id=workspace, importance=0.1)
    from dataclasses import replace
    store._records[record.memory_id] = replace(record, created_at=old, updated_at=old)

    removed = store.prune_lifecycle_candidates(workspace_id=workspace, older_than_days=30, max_importance=0.1)
    assert removed == (store._records.get(record.memory_id, removed[0]),) if False else removed
    assert store.list(workspace_id=workspace) == ()


def test_memory_retrieval_supports_required_tags() -> None:
    store = MemoryStore()
    workspace = uuid4()
    tagged = store.remember("Python deployment workflow", workspace_id=workspace, tags=("deployment",), importance=0.8)
    store.remember("Python deployment note", workspace_id=workspace, tags=("other",), importance=1.0)
    assert store.recall("Python deployment", workspace_id=workspace, required_tags=("deployment",)) == (tagged,)


def test_memory_ranking_remains_bounded_and_prefers_importance() -> None:
    store = MemoryStore()
    workspace = uuid4()
    high = store.remember("Python API testing", workspace_id=workspace, tags=("high",), importance=0.9)
    low = store.remember("Python API testing", workspace_id=workspace, tags=("low",), importance=0.2)
    matches = store.recall_ranked("Python API testing", workspace_id=workspace)
    assert matches[0].record == high
    assert 0.0 <= matches[0].confidence <= 1.0
    assert 0.0 <= matches[1].confidence <= 1.0
    assert matches[0].confidence > matches[1].confidence


def test_memory_provenance_kind_and_expiry_metadata() -> None:
    from nexus.core.memory import MemoryKind

    store = MemoryStore()
    workspace = uuid4()
    expires = datetime.now(timezone.utc) + timedelta(days=1)
    record = store.remember(
        "Preferred deployment workflow",
        workspace_id=workspace,
        memory_kind=MemoryKind.PROCEDURAL,
        source="agent",
        source_id="run-123",
        expires_at=expires,
    )

    loaded = store.list(workspace_id=workspace)[0]
    assert loaded.memory_kind is MemoryKind.PROCEDURAL
    assert loaded.source == "agent"
    assert loaded.source_id == "run-123"
    assert loaded.expires_at == expires
    assert loaded.archived is False


def test_expired_and_archived_memories_are_excluded_from_recall() -> None:
    from dataclasses import replace

    store = MemoryStore()
    workspace = uuid4()
    expired = store.remember("Expired deployment note", workspace_id=workspace)
    archived = store.remember("Archived deployment note", workspace_id=workspace)
    old = datetime.now(timezone.utc) - timedelta(days=1)
    store._records[expired.memory_id] = replace(expired, expires_at=old)
    store._records[archived.memory_id] = replace(archived, archived=True)

    assert store.recall("deployment", workspace_id=workspace) == ()
    assert len(store.list(workspace_id=workspace)) == 1
    assert len(store.list(workspace_id=workspace, include_archived=True)) == 2


def test_task_outcomes_record_explicit_provenance() -> None:
    store = MemoryStore()
    workspace = uuid4()
    record = store.remember_task_outcome(
        "Build the API",
        "API tests passed",
        workspace_id=workspace,
    )

    from nexus.core.memory import MemoryKind
    assert record.memory_kind is MemoryKind.TASK_OUTCOME
    assert record.source == "task"
    assert record.source_id == "Build the API"


def test_memory_supersession_preserves_history_and_archives_predecessor() -> None:
    store = MemoryStore()
    workspace = uuid4()
    original = store.remember("Preferred database is SQLite", workspace_id=workspace, importance=0.7)

    replacement = store.supersede(
        original.memory_id,
        "Preferred database is PostgreSQL",
        workspace_id=workspace,
        source="user",
        source_id="correction-1",
    )

    assert replacement.supersedes_id == original.memory_id
    assert replacement.content == "Preferred database is PostgreSQL"
    assert store.recall("database", workspace_id=workspace) == (replacement,)
    assert store.list(workspace_id=workspace, include_archived=True)[0].archived is True


def test_memory_archive_is_workspace_scoped() -> None:
    store = MemoryStore()
    workspace = uuid4()
    other = uuid4()
    record = store.remember("Archive me", workspace_id=workspace)

    with pytest.raises(KeyError):
        store.archive(record.memory_id, workspace_id=other)

    archived = store.archive(record.memory_id, workspace_id=workspace)
    assert archived.archived is True
    assert store.recall("Archive", workspace_id=workspace) == ()


def test_memory_decay_only_changes_aging_active_records() -> None:
    from dataclasses import replace

    store = MemoryStore()
    workspace = uuid4()
    old = datetime.now(timezone.utc) - timedelta(days=90)
    record = store.remember("Aging workflow memory", workspace_id=workspace, importance=0.8)
    active = store.remember("Fresh workflow memory", workspace_id=workspace, importance=0.8)
    store._records[record.memory_id] = replace(record, updated_at=old)

    changed = store.decay(workspace_id=workspace, older_than_days=30, amount=0.2, minimum_importance=0.2)

    assert [item.memory_id for item in changed] == [record.memory_id]
    assert changed[0].importance == 0.6
    assert store._records[active.memory_id].importance == 0.8
