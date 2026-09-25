from pathlib import Path
from uuid import uuid4

from nexus.core.events import EventStore, EventType, ExecutionEvent


def test_event_store_persists_and_filters_task_timeline(tmp_path: Path) -> None:
    store_path = tmp_path / "events.sqlite3"
    store = EventStore(store_path.as_posix())
    task_id = uuid4()
    store.append(ExecutionEvent(EventType.TASK_STARTED, task_id, "started", {"source": "test"}))
    store.append(ExecutionEvent(EventType.PLAN_CREATED, task_id, "planned", {"steps": 2}))
    store.append(ExecutionEvent(EventType.TASK_STARTED, uuid4(), "other"))

    reopened = EventStore(store_path.as_posix())
    timeline = reopened.task_timeline(task_id)
    assert [item["event_type"] for item in timeline] == ["task_started", "plan_created"]
    assert timeline[0]["data"]["source"] == "test"
    assert reopened.summary(task_id=task_id)["event_count"] == 2
