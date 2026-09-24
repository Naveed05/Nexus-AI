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

from nexus.core.workflows import evaluate_condition

def test_condition_language_is_deterministic():
    assert evaluate_condition(None,{})
    assert evaluate_condition("verification.passed == true",{"verification":{"passed":True}})
    assert evaluate_condition("run.status == 'completed'",{"run":{"status":"completed"}})
    assert not evaluate_condition("verification.passed == true",{"verification":{"passed":False}})
    assert not evaluate_condition("__import__('os').system('x') == 0",{})


import time
from datetime import datetime, timezone, timedelta
from nexus.core.workflows import WorkflowScheduler

def test_one_time_schedule_is_not_replayed(tmp_path):
    store=WorkflowStore(str(tmp_path/"w.sqlite3"))
    w=Workflow(__import__("uuid").uuid4(),"Once","Once",status="scheduled",
               steps=[WorkflowStep("a","A")],
               schedule={"run_at":(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),"enabled":True})
    store.save(w,event_type="workflow.scheduled")
    scheduler=WorkflowScheduler(store,tick=0.05)
    scheduler.start()
    time.sleep(0.18)
    scheduler.stop()
    got=store.get(w.workflow_id)
    assert got and got.schedule["enabled"] is False
    assert got.status=="running"
    assert store.event_summary(w.workflow_id)["count"]==2

def test_store_hydrates_observability_on_read(tmp_path):
    store=WorkflowStore(str(tmp_path/"w.sqlite3"))
    w=Workflow(__import__("uuid").uuid4(),"Demo","Demo",steps=[WorkflowStep("a","A")])
    store.save(w,event_type="workflow.created",detail="created")
    got=store.get(w.workflow_id)
    assert got and got.event_count==1 and got.last_event_sequence==1


def test_recurring_schedule_advances_without_replaying_same_due_time(tmp_path):
    store=WorkflowStore(str(tmp_path/"w.sqlite3"))
    first=datetime.now(timezone.utc)-timedelta(seconds=1)
    w=Workflow(__import__("uuid").uuid4(),"Recurring","Recurring",status="scheduled",
               steps=[WorkflowStep("a","A")],
               schedule={"run_at":first.isoformat(),"interval_seconds":60,"enabled":True})
    store.save(w,event_type="workflow.scheduled")
    scheduler=WorkflowScheduler(store,tick=0.05)
    scheduler.start()
    time.sleep(0.18)
    scheduler.stop()
    got=store.get(w.workflow_id)
    assert got and got.status=="running"
    assert got.schedule["enabled"] is True
    assert datetime.fromisoformat(got.schedule["run_at"]) > datetime.now(timezone.utc)-timedelta(seconds=2)
    assert store.event_summary(w.workflow_id)["count"]==2


def test_condition_can_read_step_result_context():
    assert evaluate_condition(
        "steps.verify.result.passed == true",
        {"steps":{"verify":{"status":"completed","result":{"passed":True},"error":None}}},
    )
    assert not evaluate_condition(
        "steps.verify.result.passed == true",
        {"steps":{"verify":{"status":"completed","result":{"passed":False},"error":None}}},
    )
