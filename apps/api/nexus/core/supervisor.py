from __future__ import annotations
from dataclasses import dataclass
from nexus.core.autonomy_policy import AutonomyPolicyMatrix, default_autonomy_policy
from nexus.core.collaboration_conflicts import AgentProposal, ConflictResolver, ConflictResult
from nexus.core.multi_agent import AgentRegistry, CollaborationPlan, DelegationRequest, MultiAgentCoordinator, default_agent_registry

@dataclass(frozen=True)
class SupervisionResult:
    plan: CollaborationPlan
    conflict: ConflictResult | None
    approval_required: bool
    rationale: tuple[str, ...]

class AgentSupervisor:
    """Top-level collaboration boundary; agents cannot grant themselves policy authority."""
    def __init__(self, registry: AgentRegistry | None = None, policy: AutonomyPolicyMatrix | None = None, max_workstreams: int = 8) -> None:
        self.registry = registry or default_agent_registry()
        self.policy = policy or default_autonomy_policy()
        self.coordinator = MultiAgentCoordinator(self.registry, max_workstreams)
        self.conflicts = ConflictResolver()

    def build_plan(self, objective: str, requests: tuple[DelegationRequest, ...]) -> SupervisionResult:
        plan = self.coordinator.plan(objective, requests)
        return SupervisionResult(plan, None, self.policy.approval_required("external_side_effect"),
            ("delegation is capability-aware and bounded", "external side effects remain approval-gated"))

    def resolve(self, proposals: tuple[AgentProposal, ...]) -> ConflictResult:
        return self.conflicts.resolve(proposals)
