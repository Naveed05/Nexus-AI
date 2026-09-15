from nexus.core.agent_orchestrator import AgentOrchestrator
from nexus.core.capability_router import CapabilityRouter
from nexus.core.state import PlanStep
from nexus.core.task import Task


def test_agent_orchestrator_assigns_specialized_boundaries() -> None:
    task = Task(objective="research a topic")
    steps = (
        PlanStep("understand", "understand"),
        PlanStep("research", "research"),
        PlanStep("synthesize", "synthesize"),
        PlanStep("verify", "verify", execution_required=False),
        PlanStep("deliver", "deliver", execution_required=False),
    )

    assignments = AgentOrchestrator().assign_plan(task, steps)

    assert [item.agent for item in assignments] == [
        "memory",
        "research",
        "research",
        "verification",
        "verification",
    ]
    assert [item.step_id for item in assignments] == [step.step_id for step in steps]


def test_agent_orchestrator_uses_declared_capability_for_generic_step() -> None:
    task = Task(objective="do the task", capabilities=["coding"])
    assignment = AgentOrchestrator().assign(task, PlanStep("execute", "do it"))

    assert assignment.agent == "developer"
    assert assignment.reason == "matched declared task capability"


def test_capability_router_is_deterministic_and_does_not_execute_tools() -> None:
    task = Task(objective="research machine learning")
    steps = (
        PlanStep("understand", "understand", execution_required=False),
        PlanStep("research", "research"),
        PlanStep("synthesize", "synthesize"),
        PlanStep("verify", "verify", execution_required=False),
    )

    decisions = CapabilityRouter().select_plan(task, steps)

    assert [item.capability for item in decisions] == [
        "context_understanding",
        "research",
        "synthesis",
        "verification",
    ]
    assert decisions[0].tool is None
    assert decisions[1].tool in {"research_knowledge", "search_knowledge", None}
    assert decisions == CapabilityRouter().select_plan(task, steps)


def test_capability_router_preserves_tool_safety_policy() -> None:
    task = Task(objective="inspect this repository")
    decision = CapabilityRouter().select(task, PlanStep("inspect_code", "inspect code"))

    assert decision.capability == "code_inspection"
    assert decision.tool is None
