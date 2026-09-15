from dataclasses import dataclass

from nexus.core.agent_orchestrator import AgentAssignment, AgentOrchestrator
from nexus.core.capability_router import CapabilityDecision, CapabilityRouter
from nexus.core.orchestrator import OrchestratorState
from nexus.core.task import Task


@dataclass(frozen=True)
class ExecutionDecision:
    """Immutable execution handoff assembled for one ready orchestration step."""

    step_id: str
    agent: AgentAssignment
    capability: CapabilityDecision


class ExecutionCoordinator:
    """Prepare safe, dependency-aware execution handoffs without executing tools."""

    def __init__(
        self,
        agent_orchestrator: AgentOrchestrator | None = None,
        capability_router: CapabilityRouter | None = None,
    ) -> None:
        self._agents = agent_orchestrator or AgentOrchestrator()
        self._capabilities = capability_router or CapabilityRouter()

    def prepare(self, task: Task, state: OrchestratorState, step_id: str) -> ExecutionDecision:
        step = state.plan.step_by_id(step_id)
        if step not in state.ready_steps():
            raise ValueError(f"Step '{step_id}' is not ready for execution")

        assignment = self._agents.assign(task, step)
        capability = self._capabilities.select(task, step)
        step.selected_tool = capability.tool
        step.tool_score = capability.score
        return ExecutionDecision(
            step_id=step.step_id,
            agent=assignment,
            capability=capability,
        )
