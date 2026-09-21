from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from uuid import UUID, uuid4


class AgentRole(str, Enum):
    SUPERVISOR = "supervisor"
    RESEARCHER = "researcher"
    ANALYST = "analyst"
    DEVELOPER = "developer"
    WRITER = "writer"
    VERIFIER = "verifier"


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    role: AgentRole
    capabilities: tuple[str, ...] = ()
    max_steps: int = 8

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            raise ValueError("agent_id cannot be empty")
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1")


@dataclass(frozen=True)
class Workstream:
    workstream_id: UUID
    objective: str
    agent_id: str
    dependencies: tuple[UUID, ...] = ()
    status: str = "pending"

    def __post_init__(self) -> None:
        if not self.objective.strip():
            raise ValueError("objective cannot be empty")
        if not self.agent_id.strip():
            raise ValueError("agent_id cannot be empty")


@dataclass
class CollaborationPlan:
    objective: str
    workstreams: list[Workstream] = field(default_factory=list)

    def add(self, workstream: Workstream) -> None:
        if workstream.workstream_id in {item.workstream_id for item in self.workstreams}:
            raise ValueError("duplicate workstream")
        self.workstreams.append(workstream)

    def ready(self, completed: set[UUID]) -> tuple[Workstream, ...]:
        return tuple(
            item for item in self.workstreams
            if item.status == "pending" and all(dep in completed for dep in item.dependencies)
        )


class AgentRegistry:
    """Deterministic registry for specialized agents and their declared capabilities."""

    def __init__(self, agents: tuple[AgentSpec, ...] = ()) -> None:
        self._agents: dict[str, AgentSpec] = {}
        for agent in agents:
            self.register(agent)

    def register(self, agent: AgentSpec) -> None:
        if agent.agent_id in self._agents:
            raise ValueError(f"agent already registered: {agent.agent_id}")
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> AgentSpec:
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise KeyError(f"unknown agent: {agent_id}") from exc

    def list(self) -> tuple[AgentSpec, ...]:
        return tuple(self._agents.values())

    def find_capable(self, capability: str) -> tuple[AgentSpec, ...]:
        return tuple(agent for agent in self._agents.values() if capability in agent.capabilities)


@dataclass(frozen=True)
class DelegationRequest:
    objective: str
    required_capability: str
    requester: str
    workstream_id: UUID = field(default_factory=uuid4)


class MultiAgentCoordinator:
    """Builds bounded, capability-aware collaboration plans without granting agents policy authority."""

    def __init__(self, registry: AgentRegistry, max_workstreams: int = 8) -> None:
        if max_workstreams < 1:
            raise ValueError("max_workstreams must be at least 1")
        self.registry = registry
        self.max_workstreams = max_workstreams

    def delegate(self, request: DelegationRequest) -> Workstream:
        candidates = self.registry.find_capable(request.required_capability)
        if not candidates:
            raise LookupError(f"no agent supports capability: {request.required_capability}")
        if request.requester == candidates[0].agent_id:
            raise ValueError("agent cannot delegate to itself")
        return Workstream(
            workstream_id=request.workstream_id,
            objective=request.objective,
            agent_id=candidates[0].agent_id,
        )

    def plan(self, objective: str, requests: tuple[DelegationRequest, ...]) -> CollaborationPlan:
        if not objective.strip():
            raise ValueError("objective cannot be empty")
        if len(requests) > self.max_workstreams:
            raise ValueError("workstream limit exceeded")
        plan = CollaborationPlan(objective=objective.strip())
        for request in requests:
            plan.add(self.delegate(request))
        return plan


def default_agent_registry() -> AgentRegistry:
    return AgentRegistry((
        AgentSpec("supervisor", AgentRole.SUPERVISOR, ("planning", "coordination")),
        AgentSpec("researcher", AgentRole.RESEARCHER, ("research", "retrieval")),
        AgentSpec("analyst", AgentRole.ANALYST, ("analysis", "data")),
        AgentSpec("developer", AgentRole.DEVELOPER, ("coding", "testing")),
        AgentSpec("writer", AgentRole.WRITER, ("writing", "synthesis")),
        AgentSpec("verifier", AgentRole.VERIFIER, ("verification", "evaluation")),
    ))
