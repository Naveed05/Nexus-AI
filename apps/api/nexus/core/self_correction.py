from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass(frozen=True)
class CorrectionAction:
    issue: str
    action: str
    expected_signal: str


@dataclass(frozen=True)
class CorrectionPlan:
    actions: tuple[CorrectionAction, ...]
    rationale: str


class SelfCorrectionPlanner:
    """Turns verification issues into bounded, explainable corrective actions."""

    def plan(self, issues: Sequence[str], *, available_actions: Sequence[str]) -> CorrectionPlan:
        actions = tuple(available_actions)
        planned: list[CorrectionAction] = []
        for issue in issues:
            clean = issue.strip()
            if not clean:
                continue
            if not actions:
                continue
            selected = actions[0]
            planned.append(CorrectionAction(clean, selected, f"verification no longer reports: {clean}"))
        rationale = "No corrective action required." if not planned else f"Mapped {len(planned)} verification issue(s) to bounded actions."
        return CorrectionPlan(tuple(planned), rationale)
