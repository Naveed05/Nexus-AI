from dataclasses import dataclass

from nexus.core.state import PlanStep
from nexus.core.tools import ToolSpec, tool_registry


@dataclass(frozen=True)
class ToolDecision:
    """Explainable tool-selection metadata; no hidden model reasoning."""

    tool: ToolSpec | None
    score: float
    reasons: tuple[str, ...]


class ToolSelector:
    """Selects the best registered tool for an executable plan step."""

    _signals: dict[str, tuple[str, ...]] = {
        "calculator": ("calculate", "calculation", "compute", "arithmetic", "sum", "average"),
        "profile_dataset": ("inspect", "profile", "schema", "missing", "quality", "dataset"),
        "analyze_dataset": ("analyze", "analysis", "eda", "explore", "correlation", "dataset"),
        "baseline_ml": ("machine learning", "model", "train", "classification", "regression", "predict"),
    }

    def decide(self, step: PlanStep) -> ToolDecision:
        text = f"{step.step_id} {step.objective}".lower()
        candidates: list[tuple[float, ToolSpec, list[str]]] = []

        for tool in tool_registry.all():
            signals = self._signals.get(tool.name, ())
            matched = [signal for signal in signals if signal in text]
            if not matched:
                continue
            score = min(95.0, 50.0 + len(matched) * 10.0)
            candidates.append(
                (
                    score,
                    tool,
                    [f"matched {len(matched)} step signals: {', '.join(matched[:3])}"],
                )
            )

        if not candidates:
            return ToolDecision(
                tool=None,
                score=0.0,
                reasons=("no registered tool matches the step objective",),
            )

        candidates.sort(key=lambda item: (-item[0], item[1].name))
        score, tool, reasons = candidates[0]
        return ToolDecision(tool=tool, score=score, reasons=tuple(reasons))

    def select(self, step: PlanStep) -> ToolSpec | None:
        """Backward-compatible shorthand returning only the selected tool."""
        return self.decide(step).tool


tool_selector = ToolSelector()
