import json
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import UUID

from nexus.core.orchestrator import OrchestratorState, TaskPlan
from nexus.core.state import PlanStep, StepStatus


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, StepStatus):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return repr(value)


class OrchestrationCheckpoint:
    """Persist and restore bounded orchestration state as a JSON checkpoint."""

    def save(self, state: OrchestratorState, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "plan": {
                "task_id": str(state.plan.task_id),
                "objective": state.plan.objective,
                "metadata": _json_safe(state.plan.metadata),
                "steps": [
                    {
                        "step_id": step.step_id,
                        "objective": step.objective,
                        "status": step.status.value,
                        "result": _json_safe(step.result),
                        "observation": _json_safe(step.observation),
                        "error": step.error,
                        "attempts": step.attempts,
                        "depends_on": list(step.depends_on),
                        "execution_required": step.execution_required,
                        "selected_tool": step.selected_tool,
                        "tool_score": step.tool_score,
                    }
                    for step in state.plan.steps
                ],
            },
            "status": state.status,
            "current_step_id": state.current_step_id,
            "history": list(state.history),
        }
        target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return target

    def load(self, path: str | Path) -> OrchestratorState:
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        plan_data = payload["plan"]
        steps = tuple(
            PlanStep(
                step_id=item["step_id"],
                objective=item["objective"],
                status=StepStatus(item["status"]),
                result=item.get("result"),
                observation=item.get("observation"),
                error=item.get("error"),
                attempts=int(item.get("attempts", 0)),
                depends_on=tuple(item.get("depends_on", ())),
                execution_required=bool(item.get("execution_required", True)),
                selected_tool=item.get("selected_tool"),
                tool_score=float(item.get("tool_score", 0.0)),
            )
            for item in plan_data["steps"]
        )
        plan = TaskPlan(
            task_id=UUID(plan_data["task_id"]),
            objective=plan_data["objective"],
            steps=steps,
            metadata=dict(plan_data.get("metadata", {})),
        )
        return OrchestratorState(
            plan=plan,
            status=payload.get("status", "ready"),
            current_step_id=payload.get("current_step_id"),
            history=list(payload.get("history", [])),
        )
