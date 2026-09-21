from uuid import uuid4

import pytest

from nexus.core.multi_agent import (
    AgentRegistry,
    AgentRole,
    AgentSpec,
    DelegationRequest,
    MultiAgentCoordinator,
    default_agent_registry,
)


def test_default_registry_contains_specialized_roles() -> None:
    roles = {agent.role for agent in default_agent_registry().list()}
    assert AgentRole.RESEARCHER in roles
    assert AgentRole.ANALYST in roles
    assert AgentRole.DEVELOPER in roles
    assert AgentRole.VERIFIER in roles


def test_registry_capability_discovery_is_deterministic() -> None:
    registry = default_agent_registry()
    assert [item.agent_id for item in registry.find_capable("research")] == ["researcher"]
    assert registry.get("developer").role is AgentRole.DEVELOPER


def test_coordinator_delegates_to_capable_specialist() -> None:
    coordinator = MultiAgentCoordinator(default_agent_registry())
    request = DelegationRequest(
        objective="Find primary evidence",
        required_capability="research",
        requester="supervisor",
    )
    workstream = coordinator.delegate(request)
    assert workstream.agent_id == "researcher"
    assert workstream.status == "pending"


def test_coordinator_rejects_self_delegation() -> None:
    coordinator = MultiAgentCoordinator(default_agent_registry())
    with pytest.raises(ValueError, match="cannot delegate"):
        coordinator.delegate(
            DelegationRequest(
                objective="Coordinate",
                required_capability="coordination",
                requester="supervisor",
            )
        )


def test_plan_enforces_workstream_bound() -> None:
    coordinator = MultiAgentCoordinator(default_agent_registry(), max_workstreams=1)
    with pytest.raises(ValueError, match="limit"):
        coordinator.plan(
            "goal",
            (
                DelegationRequest("research", "research", "supervisor"),
                DelegationRequest("verify", "verification", "supervisor"),
            ),
        )


def test_plan_tracks_dependency_ready_workstreams() -> None:
    coordinator = MultiAgentCoordinator(default_agent_registry())
    first = DelegationRequest("research", "research", "supervisor")
    second_id = uuid4()
    plan = coordinator.plan("goal", (first,))
    dependent = plan.workstreams[0]
    assert plan.ready(set()) == (dependent,)
    assert plan.ready({dependent.workstream_id}) == ()
    assert dependent.workstream_id != second_id
