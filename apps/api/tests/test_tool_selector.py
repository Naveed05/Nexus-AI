from nexus.core.state import PlanStep
from nexus.core.tool_selector import ToolSelector


def test_selector_chooses_profile_tool_for_data_inspection() -> None:
    step = PlanStep("inspect_data", "Inspect the dataset schema and missing values.")
    decision = ToolSelector().decide(step)

    assert decision.tool is not None
    assert decision.tool.name == "profile_dataset"
    assert decision.score > 0
    assert decision.reasons


def test_selector_chooses_analysis_tool_for_eda() -> None:
    step = PlanStep("analyze_data", "Analyze the dataset with EDA and correlations.")
    decision = ToolSelector().decide(step)

    assert decision.tool is not None
    assert decision.tool.name == "analyze_dataset"


def test_selector_chooses_ml_tool_for_training() -> None:
    step = PlanStep("train_model", "Train a classification model and predict the target.")
    decision = ToolSelector().decide(step)

    assert decision.tool is not None
    assert decision.tool.name == "baseline_ml"


def test_selector_returns_no_tool_when_no_match_exists() -> None:
    step = PlanStep("summarize", "Write a concise narrative summary.")
    decision = ToolSelector().decide(step)

    assert decision.tool is None
    assert decision.score == 0.0
    assert decision.reasons == ("no registered tool matches the step objective",)
