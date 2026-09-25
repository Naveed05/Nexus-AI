from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from .agent_workflows import AgentWorkflow, AgentWorkflowOrchestrator, WorkItemStatus
from .collaboration_audit import CollaborationAuditLog
from .jobs import DurableJobManager, JobStatus


@dataclass(frozen=True)
class CollaborationDispatch:
    workflow_id: UUID
    dispatched: tuple[dict[str, str], ...]
    active: int


class CollaborationRuntime:
    """Connects the durable agent-workflow DAG to the durable job execution plane.

    The workflow remains the source of truth for dependencies; jobs are execution
    units. Completion is imported from the job plane only after the job reaches a
    terminal state, and every binding is recorded in provenance.
    """

    def __init__(
        self,
        orchestrator: AgentWorkflowOrchestrator,
        jobs: DurableJobManager,
        audit: CollaborationAuditLog,
    ) -> None:
        self.orchestrator = orchestrator
        self.jobs = jobs
        self.audit = audit

    @staticmethod
    def _job_ref(item) -> UUID | None:
        for ref in item.input_refs:
            if ref.startswith("job:"):
                try:
                    return UUID(ref[4:])
                except ValueError:
                    return None
        return None

    def dispatch(self, workflow_id: UUID) -> CollaborationDispatch:
        workflow = self.orchestrator.store.get(workflow_id)
        if workflow is None:
            raise KeyError("unknown agent workflow")
        selected = self.orchestrator.dispatch(workflow_id)
        bindings: list[dict[str, str]] = []
        for item in selected:
            job = self.jobs.submit(
                item.objective,
                owner_id=workflow.owner_id,
                context=f"agent_id={item.agent_id}; workflow_id={workflow.workflow_id}; work_item_id={item.item_id}",
                risk_level="low",
            )
            item.input_refs = [ref for ref in item.input_refs if not ref.startswith("job:")]
            item.input_refs.append(f"job:{job.job_id}")
            item.provenance = {
                **item.provenance,
                "execution_plane": "durable-job",
                "job_id": str(job.job_id),
                "agent_id": item.agent_id,
                "bound_at": datetime.now(timezone.utc).isoformat(),
            }
            # Persist the binding without changing the work item's running state.
            self.orchestrator.store.save(
                workflow,
                event_type="execution.job.bound",
                detail=f"work item bound to durable job {job.job_id}",
                item_id=item.item_id,
            )
            self.audit.append(
                "collaboration.job.bound",
                workflow.owner_id,
                {"workflow_id": str(workflow_id), "work_item_id": str(item.item_id), "job_id": str(job.job_id), "agent_id": item.agent_id},
            )
            bindings.append({"item_id": str(item.item_id), "job_id": str(job.job_id), "agent_id": item.agent_id})
        return CollaborationDispatch(workflow_id, tuple(bindings), len([i for i in workflow.items if i.status == WorkItemStatus.RUNNING]))

    def sync(self, workflow_id: UUID) -> dict[str, Any]:
        workflow = self.orchestrator.store.get(workflow_id)
        if workflow is None:
            raise KeyError("unknown agent workflow")
        changed: list[dict[str, str]] = []
        for item in workflow.items:
            if item.status != WorkItemStatus.RUNNING:
                continue
            job_id = self._job_ref(item)
            if job_id is None:
                continue
            job = self.jobs.get(job_id)
            if job.status == JobStatus.COMPLETED:
                output_refs = []
                if job.artifact_id:
                    output_refs.append(f"artifact:{job.artifact_id}")
                if job.run_id:
                    output_refs.append(f"run:{job.run_id}")
                self.orchestrator.complete(
                    workflow_id,
                    item.item_id,
                    output_refs=output_refs,
                    provenance={"job_id": str(job.job_id), "job_status": job.status.value},
                )
                changed.append({"item_id": str(item.item_id), "state": "completed"})
            elif job.status == JobStatus.FAILED:
                self.orchestrator.fail(workflow_id, item.item_id, job.error or "execution job failed")
                changed.append({"item_id": str(item.item_id), "state": "failed"})
            elif job.status == JobStatus.CANCELLED:
                self.orchestrator.fail(workflow_id, item.item_id, "execution job was cancelled")
                changed.append({"item_id": str(item.item_id), "state": "failed"})
        current = self.orchestrator.store.get(workflow_id)
        self.audit.append(
            "collaboration.sync",
            current.owner_id if current else "system",
            {"workflow_id": str(workflow_id), "changed": changed},
        )
        return {"workflow": current, "changed": changed, "health": self.orchestrator.health(current) if current else None}
