from pathlib import Path

from nexus.core.agent_workflows import AgentWorkItem, AgentWorkflowOrchestrator, AgentWorkflowStore
from nexus.core.collaboration_audit import CollaborationAuditLog
from nexus.core.collaboration_runtime import CollaborationRuntime
from nexus.core.jobs import DurableJobManager, JobStatus, JobStore


def test_collaboration_runtime_binds_dag_work_to_durable_jobs(tmp_path: Path) -> None:
    workflow_store = AgentWorkflowStore(tmp_path / "workflows.sqlite3")
    jobs = JobStore(tmp_path / "jobs.sqlite3")

    def executor(job):
        return {"ok": True, "job_id": str(job.job_id)}

    manager = DurableJobManager(jobs, executor, auto_start=False)
    audit = CollaborationAuditLog(tmp_path / "audit.sqlite3")
    orchestrator = AgentWorkflowOrchestrator(workflow_store)
    runtime = CollaborationRuntime(orchestrator, manager, audit)

    workflow = orchestrator.create(
        "research then verify",
        [
            AgentWorkItem(__import__("uuid").uuid4(), "research the source", "research"),
            AgentWorkItem(__import__("uuid").uuid4(), "verify the source", "verifier"),
        ],
        "u1",
        1,
    )
    dispatched = runtime.dispatch(workflow.workflow_id)
    assert len(dispatched.dispatched) == 1

    current = workflow_store.get(workflow.workflow_id)
    job_id = next(i for i in current.items if i.status.value == "running").input_refs[-1].split(":", 1)[1]
    job = jobs.get(__import__("uuid").UUID(job_id))
    job.status = JobStatus.COMPLETED
    job.result = {"verified": True}
    jobs.save(job)

    synced = runtime.sync(workflow.workflow_id)
    assert synced["changed"][0]["state"] == "completed"
    assert len(audit.list()) >= 2
    assert audit.verify()[0] is True
