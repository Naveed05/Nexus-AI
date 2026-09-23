from datetime import datetime, timezone, timedelta
from nexus.core.workflows import Workflow, WorkflowStep, WorkflowStepStatus, WorkflowStore, WorkflowValidationError, validate_workflow, workflow_payload

def test_workflow_validation_rejects_missing_dependency():
    steps=[WorkflowStep("a","A",["missing"])]
    try: validate_workflow(steps)
    except WorkflowValidationError: return
    assert False

def test_workflow_validation_rejects_cycle():
    try: validate_workflow([WorkflowStep("a","A",["b"]),WorkflowStep("b","B",["a"])])
    except WorkflowValidationError: return
    assert False

def test_workflow_store_roundtrip(tmp_path):
    store=WorkflowStore(str(tmp_path/"w.sqlite3"))
    w=Workflow(__import__("uuid").uuid4(),"Demo","Build demo",steps=[WorkflowStep("a","A"),WorkflowStep("b","B",["a"])])
    store.save(w); got=store.get(w.workflow_id)
    assert got and got.steps[1].depends_on==["a"]

def test_workflow_payload_is_api_safe(tmp_path):
    store=WorkflowStore(str(tmp_path/"w.sqlite3"))
    w=Workflow(__import__("uuid").uuid4(),"Demo","Build demo",steps=[WorkflowStep("a","A")])
    p=workflow_payload(store.save(w))
    assert p["status"]=="draft" and p["steps"][0]["status"]=="pending"
