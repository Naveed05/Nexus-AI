from uuid import uuid4
import pytest
from nexus.core.agent_workflows import (
    AgentWorkflowStore,AgentWorkflowOrchestrator,AgentWorkItem,WorkItemStatus,
    AgentWorkflowStatus,AgentWorkflowValidationError,AgentWorkflowOrchestrationError,
)


def make_items():
    a=uuid4(); b=uuid4(); c=uuid4()
    return [
        AgentWorkItem(a,"research","researcher"),
        AgentWorkItem(b,"analyze","analyst",[a]),
        AgentWorkItem(c,"verify","verifier",[b]),
    ]


def test_validation_rejects_cycle(tmp_path):
    a,b=uuid4(),uuid4()
    items=[AgentWorkItem(a,"a","researcher",[b]),AgentWorkItem(b,"b","analyst",[a])]
    with pytest.raises(AgentWorkflowValidationError,match="cycle"):
        AgentWorkflowOrchestrator(AgentWorkflowStore(str(tmp_path/"db.sqlite3"))).create("goal",items)


def test_dispatch_respects_dependencies_and_parallel_bound(tmp_path):
    store=AgentWorkflowStore(str(tmp_path/"db.sqlite3")); orch=AgentWorkflowOrchestrator(store)
    w=orch.create("goal",make_items(),max_parallel=1)
    selected=orch.dispatch(w.workflow_id)
    assert len(selected)==1 and selected[0].agent_id=="researcher"
    w=store.get(w.workflow_id)
    assert w.status is AgentWorkflowStatus.RUNNING
    assert sum(i.status is WorkItemStatus.RUNNING for i in w.items)==1


def test_completion_unlocks_next_wave(tmp_path):
    store=AgentWorkflowStore(str(tmp_path/"db.sqlite3")); orch=AgentWorkflowOrchestrator(store)
    w=orch.create("goal",make_items(),max_parallel=2)
    first=orch.dispatch(w.workflow_id)[0]
    orch.complete(w.workflow_id,first.item_id,["artifact:research"],{"source":"researcher"})
    second=orch.dispatch(w.workflow_id)
    assert len(second)==1 and second[0].agent_id=="analyst"
    assert store.get(w.workflow_id).items[1].input_refs==[]


def test_failure_retry_and_recovery(tmp_path):
    store=AgentWorkflowStore(str(tmp_path/"db.sqlite3")); orch=AgentWorkflowOrchestrator(store)
    w=orch.create("goal",make_items())
    item=orch.dispatch(w.workflow_id)[0]
    orch.fail(w.workflow_id,item.item_id,"temporary")
    assert store.get(w.workflow_id).status is AgentWorkflowStatus.FAILED
    orch.retry(w.workflow_id,item.item_id)
    assert store.get(w.workflow_id).status is AgentWorkflowStatus.READY
    assert store.get(w.workflow_id).items[0].status is WorkItemStatus.PENDING


def test_terminal_workflow_cannot_dispatch(tmp_path):
    store=AgentWorkflowStore(str(tmp_path/"db.sqlite3")); orch=AgentWorkflowOrchestrator(store)
    w=orch.create("goal",make_items())
    orch.cancel(w.workflow_id)
    with pytest.raises(AgentWorkflowOrchestrationError,match="terminal"):
        orch.dispatch(w.workflow_id)


def test_persistence_events_and_health(tmp_path):
    path=str(tmp_path/"db.sqlite3"); store=AgentWorkflowStore(path); orch=AgentWorkflowOrchestrator(store)
    w=orch.create("goal",make_items())
    orch.dispatch(w.workflow_id)
    events=store.events(w.workflow_id)
    assert events and events[0]["event_type"]=="workstream.dispatched"
    health=orch.health(store.get(w.workflow_id))
    assert health["active_count"]==1 and health["needs_operator"] is False
    restored=AgentWorkflowStore(path).get(w.workflow_id)
    assert restored and restored.version>=2


def test_metrics_are_bounded_and_deterministic(tmp_path):
    store=AgentWorkflowStore(str(tmp_path/"db.sqlite3")); orch=AgentWorkflowOrchestrator(store)
    orch.create("one",make_items())
    orch.create("two",make_items())
    metrics=orch.metrics(store.list(500))
    assert metrics["workflow_count"]==2
    assert metrics["active_workflow_count"]==2
    assert 0 <= metrics["completion_rate"] <= 1
