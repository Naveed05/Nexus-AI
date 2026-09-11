from nexus.core.state import PlanStep
from nexus.core.task import Task
from nexus.core.tool_intelligence import ToolSelector
from nexus.core.tools import ToolRegistry, ToolSpec, calculator


def test_selector_maps_data_inspection_to_profile_tool() -> None:
    decision = ToolSelector().select(
        Task(objective="Inspect this dataset"),
        PlanStep("inspect_data", "Inspect the dataset"),
    )
    assert decision.tool is not None
    assert decision.tool.name == "profile_dataset"
    assert decision.score == 100.0
    assert decision.reasons


def test_selector_maps_analysis_to_analysis_tool() -> None:
    decision = ToolSelector().select(
        Task(objective="Analyze this dataset"),
        PlanStep("analyze_data", "Analyze this dataset"),
    )
    assert decision.tool is not None
    assert decision.tool.name == "analyze_dataset"


def test_selector_uses_reference_tool_when_dataset_id_is_in_context() -> None:
    decision = ToolSelector().select(
        Task(objective="Inspect this dataset", context="dataset_id=123"),
        PlanStep("inspect_data", "Inspect the registered dataset"),
    )
    assert decision.tool is not None
    assert decision.tool.name == "profile_dataset_by_id"
    assert any("dataset reference detected" in reason for reason in decision.reasons)


def test_selector_returns_no_tool_when_step_has_no_match() -> None:
    decision = ToolSelector().select(
        Task(objective="Research the latest approaches"),
        PlanStep("research", "Research the latest approaches"),
    )
    assert decision.tool is None
    assert decision.score == 0.0
    assert "no registered tool" in decision.reasons[0]


def test_selector_works_with_custom_registry() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="calculator",
            description="Calculate arithmetic",
            input_schema={
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
                "additionalProperties": False,
            },
            risk_level="low",
            handler=calculator,
        )
    )
    decision = ToolSelector(registry).select(
        Task(objective="Do a calculation"),
        PlanStep("execute", "Calculate 2 + 2"),
    )
    assert decision.tool is not None
    assert decision.tool.name == "calculator"
