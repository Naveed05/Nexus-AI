from datetime import datetime, timezone
from uuid import uuid4

import pytest

from nexus.core.workflows import (
    Workflow,
    WorkflowControlError,
    WorkflowControlPlane,
    WorkflowStep,
    WorkflowStepStatus,
    WorkflowStore,
    workflow_health,
    workflow_metrics,
)


def make_workflow(store, status="draft"):
    w=Workflow(
        uuid4(),
        "Control",
        "Control workflow",
        steps=[
            WorkflowStep("a","A"),
            WorkflowStep("b","B",depends_on=["a"]),
        ],
        status=status,
    )
    store.save(w, event_type="workflow.created")
    return w


def test_control_plane_commands_are_idempotent(tmp_path):
    store=WorkflowStore(str(tmp_path/"workflow.sqlite3"))
    control=WorkflowControlPlane(store)
    w=make_workflow(store)
    first_w, first=control.execute(w.workflow_id,"start",idempotency_key="cmd-1")
    second_w, second=control.execute(w.workflow_id,"start",idempotency_key="cmd-1")
    assert first.command_id==second.command_id
    assert first_w.status==second_w.status=="running"
    assert len(control.history(w.workflow_id))==1


def test_control_plane_pause_resume_cancel(tmp_path):
    store=WorkflowStore(str(tmp_path/"workflow.sqlite3"))
    control=WorkflowControlPlane(store)
    w=make_workflow(store)
    control.execute(w.workflow_id,"start",idempotency_key="start")
    paused,_=control.execute(w.workflow_id,"pause",idempotency_key="pause")
    assert paused.status=="paused"
    resumed,_=control.execute(w.workflow_id,"resume",idempotency_key="resume")
    assert resumed.status=="running"
    cancelled,_=control.execute(w.workflow_id,"cancel",idempotency_key="cancel")
    assert cancelled.status=="cancelled"


def test_control_plane_retry_step_and_restart(tmp_path):
    store=WorkflowStore(str(tmp_path/"workflow.sqlite3"))
    control=WorkflowControlPlane(store)
    w=make_workflow(store,status="failed")
    w.steps[0].status=WorkflowStepStatus.FAILED
    w.steps[0].error="boom"
    store.save(w,event_type="workflow.failed")
    retried,_=control.execute(w.workflow_id,"retry_step",step_id="a",idempotency_key="retry-a")
    assert retried.status=="running"
    assert retried.steps[0].status==WorkflowStepStatus.PENDING
    restarted,_=control.execute(w.workflow_id,"restart",idempotency_key="restart")
    assert restarted.status=="running"
    assert all(s.status==WorkflowStepStatus.PENDING for s in restarted.steps)


def test_control_plane_rejects_invalid_transitions_and_keys(tmp_path):
    store=WorkflowStore(str(tmp_path/"workflow.sqlite3"))
    control=WorkflowControlPlane(store)
    w=make_workflow(store)
    with pytest.raises(WorkflowControlError):
        control.execute(w.workflow_id,"resume",idempotency_key="bad")
    control.execute(w.workflow_id,"start",idempotency_key="same")
    with pytest.raises(WorkflowControlError):
        control.execute(w.workflow_id,"pause",idempotency_key="same")


def test_skip_step_unblocks_downstream(tmp_path):
    store=WorkflowStore(str(tmp_path/"workflow.sqlite3"))
    control=WorkflowControlPlane(store)
    w=make_workflow(store)
    control.execute(w.workflow_id,"start",idempotency_key="start")
    skipped,_=control.execute(w.workflow_id,"skip_step",step_id="a",idempotency_key="skip-a")
    assert skipped.steps[0].status==WorkflowStepStatus.SKIPPED
    assert skipped.steps[1].status==WorkflowStepStatus.PENDING


def test_workflow_metrics_and_health(tmp_path):
    store=WorkflowStore(str(tmp_path/"workflow.sqlite3"))
    healthy=make_workflow(store,status="running")
    healthy.steps[0].status=WorkflowStepStatus.COMPLETED
    healthy.steps[1].status=WorkflowStepStatus.RUNNING
    store.save(healthy,event_type="workflow.running")
    failed=make_workflow(store,status="failed")
    failed.steps[0].status=WorkflowStepStatus.FAILED
    store.save(failed,event_type="workflow.failed")
    metrics=workflow_metrics([healthy,failed])
    assert metrics["workflow_count"]==2
    assert metrics["status_counts"]["failed"]==1
    assert metrics["step_status_counts"]["failed"]==1
    assert workflow_health(failed)["needs_operator"] is True
    assert workflow_health(healthy)["healthy"] is True
