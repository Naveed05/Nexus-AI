from uuid import uuid4

import pytest

from nexus.core.distributed_state import DistributedStateStore, StateConflictError, state_key


def test_versioned_state_round_trip(tmp_path):
    store = DistributedStateStore(str(tmp_path / "state.sqlite3"))
    record = store.put("run:1", {"status": "queued"})
    assert record.version == 1
    assert store.get("run:1").value["status"] == "queued"
    updated = store.put("run:1", {"status": "claimed"}, expected_version=1)
    assert updated.version == 2
    assert store.get("run:1").version == 2


def test_compare_and_swap_rejects_stale_writer(tmp_path):
    store = DistributedStateStore(str(tmp_path / "state.sqlite3"))
    record = store.put("run:1", {"status": "queued"})
    store.put("run:1", {"status": "claimed"}, expected_version=record.version)
    with pytest.raises(StateConflictError):
        store.put("run:1", {"status": "failed"}, expected_version=record.version)


def test_delete_and_namespaced_keys(tmp_path):
    store = DistributedStateStore(str(tmp_path / "state.sqlite3"))
    key = state_key("workspace", uuid4())
    record = store.put(key, {"ready": True})
    assert store.delete(key, expected_version=record.version)
    assert store.get(key) is None
    assert not store.delete(key)
