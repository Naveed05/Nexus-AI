from __future__ import annotations

import pytest

from nexus.core.production_runtime import ProductionRunPolicy, ProductionRuntime
from nexus.core.runtime import RunBudget, RunStatus
from nexus.core.task import Task, TaskStatus


class FakeEngine:
    def run(self, task: Task, *, control):
        control.consume_step()

        class Result:
            def __init__(self) -> None:
                self.task = task.model_copy(update={"status": TaskStatus.COMPLETED})
                self.events = ()

        return Result()


def test_production_runtime_persists_completed_run(tmp_path) -> None:
    runtime = ProductionRuntime(store_path=str(tmp_path / "runs.sqlite3"), engine=FakeEngine())
    task = Task(objective="production smoke test")

    run, _ = runtime.start(task, idempotency_key="smoke-1")

    assert run.status is RunStatus.COMPLETED
    assert run.steps_completed == 1
    assert runtime.health()["active_runs"] == 0

    restarted = ProductionRuntime(store_path=str(tmp_path / "runs.sqlite3"), engine=FakeEngine())
    loaded = restarted.status(run.run_id)
    assert loaded.status is RunStatus.COMPLETED
    assert loaded.metadata["idempotency_key"] == "smoke-1"


def test_production_runtime_rejects_duplicate_idempotency_key(tmp_path) -> None:
    runtime = ProductionRuntime(store_path=str(tmp_path / "runs.sqlite3"), engine=FakeEngine())
    task = Task(objective="duplicate test")

    runtime.start(task, idempotency_key="same-key")

    with pytest.raises(ValueError, match="idempotency key"):
        runtime.start(task, idempotency_key="same-key")


def test_production_runtime_enforces_concurrency_policy(tmp_path, monkeypatch) -> None:
    runtime = ProductionRuntime(
        store_path=str(tmp_path / "runs.sqlite3"),
        engine=FakeEngine(),
        policy=ProductionRunPolicy(max_concurrent_runs=1),
    )
    runtime._active = 1

    with pytest.raises(RuntimeError, match="concurrency limit"):
        runtime.start(Task(objective="overloaded"))

    assert runtime.health()["capacity_available"] == 0


def test_production_runtime_rejects_empty_idempotency_key(tmp_path) -> None:
    runtime = ProductionRuntime(store_path=str(tmp_path / "runs.sqlite3"), engine=FakeEngine())

    with pytest.raises(ValueError, match="idempotency_key"):
        runtime.start(Task(objective="validation"), idempotency_key=" ")
