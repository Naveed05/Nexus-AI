from datetime import datetime, timezone
from nexus.core.workflows import (
    Workflow, WorkflowStep, WorkflowStepStatus, WorkflowStore,
    WorkflowValidationError, validate_workflow, ready_steps, workflow_payload
)

def test_workflow_event_journal_roundtrip(tmp_path):
    store=WorkflowStore(str(tmp_path/"w.sqlite3"))
    w=Workflow(__import__("uuid").uuid4(),"Demo","Build demo",steps=[WorkflowStep("a","A")])
    store.save(w,event_type="workflow.created",detail="created")
    w.steps[0].status=WorkflowStepStatus.COMPLETED
    w.status="completed"
    store.save(w,event_type="workflow.completed",detail="done",step_id="a")
    events=store.events(w.workflow_id)
    assert len(events)==2
    assert events[0].event_type=="workflow.completed"
    assert events[0].step_id=="a"
    assert store.event_summary(w.workflow_id)["count"]==2

def test_ready_steps_respects_dependencies():
    a=WorkflowStep("a","A",status=WorkflowStepStatus.COMPLETED)
    b=WorkflowStep("b","B",depends_on=["a"])
    c=WorkflowStep("c","C",depends_on=["a"])
    w=Workflow(__import__("uuid").uuid4(),"Demo","Demo",steps=[a,b,c])
    assert [s.step_id for s in ready_steps(w)]==["b","c"]

def test_ready_steps_blocks_failed_dependency():
    a=WorkflowStep("a","A",status=WorkflowStepStatus.FAILED)
    b=WorkflowStep("b","B",depends_on=["a"])
    w=Workflow(__import__("uuid").uuid4(),"Demo","Demo",steps=[a,b])
    assert ready_steps(w)==[]

def test_workflow_payload_exposes_delivery_observability(tmp_path):
    store=WorkflowStore(str(tmp_path/"w.sqlite3"))
    w=Workflow(__import__("uuid").uuid4(),"Demo","Demo",steps=[WorkflowStep("a","A")])
    store.save(w,event_type="workflow.created",detail="created")
    p=workflow_payload(w,store)
    assert p["event_count"]==1
    assert p["last_event_sequence"]==1
    assert p["last_event_at"]
