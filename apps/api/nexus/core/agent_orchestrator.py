from dataclasses import dataclass

from nexus.core.state import PlanStep
from nexus.core.task import Task


@dataclass(frozen=True)
class AgentAssignment:
    """Deterministic assignment of a plan step to a NEXUS agent boundary."""

    step_id: str
    agent: str
    reason: str


class AgentOrchestrator:
    """Select the NEXUS agent responsible for each plan step without executing it."""

    _step_agents: dict[str, str] = {
        "inspect_code": "developer",
        "implement": "developer",
        "research": "research",
        "synthesize": "research",
        "inspect_data": "data",
        "analyze_data": "data",
        "verify": "verification",
        "deliver": "verification",
        "understand": "memory",
    }

    _capability_agents: dict[str, str] = {
        "coding": "developer",
        "developer": "developer",
        "research": "research",
        "web_research": "research",
        "data": "data",
        "data_analysis": "data",
        "memory": "memory",
        "verification": "verification",
    }

    def assign(self, task: Task, step: PlanStep) -> AgentAssignment:
        requested = {value.strip().lower() for value in task.capabilities if value.strip()}
        agent = self._step_agents.get(step.step_id)
        reason = f"matched plan step '{step.step_id}'"

        if agent is None and requested:
            matches = sorted(
                self._capability_agents[capability]
                for capability in requested
                if capability in self._capability_agents
            )
            if matches:
                agent = matches[0]
                reason = "matched declared task capability"

        if agent is None:
            agent = "general"
            reason = "no specialized agent boundary matched"

        return AgentAssignment(step_id=step.step_id, agent=agent, reason=reason)

    def assign_plan(self, task: Task, steps: tuple[PlanStep, ...]) -> tuple[AgentAssignment, ...]:
        """Assign every step deterministically while preserving plan order."""
        return tuple(self.assign(task, step) for step in steps)
