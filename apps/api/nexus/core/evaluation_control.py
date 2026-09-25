"""Phase 62: durable evaluation quality gates and regression decisions.

This layer turns persisted evaluation history into an explicit, deterministic
release-quality decision without coupling evaluation to a particular model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus.core.evaluation_intelligence import EvaluationIntelligenceStore, compare_reports


@dataclass(frozen=True)
class EvaluationPolicy:
    """Absolute quality floors and maximum tolerated regression deltas."""

    minimum_pass_rate: float = 0.90
    minimum_check_score: float = 0.85
    minimum_grounding_score: float = 0.80
    maximum_pass_rate_drop: float = 0.05
    maximum_check_score_drop: float = 0.05
    maximum_grounding_score_drop: float = 0.05

    def __post_init__(self) -> None:
        bounded = (
            self.minimum_pass_rate,
            self.minimum_check_score,
            self.minimum_grounding_score,
        )
        if any(value < 0 or value > 1 for value in bounded):
            raise ValueError("minimum quality thresholds must be between 0 and 1")
        drops = (
            self.maximum_pass_rate_drop,
            self.maximum_check_score_drop,
            self.maximum_grounding_score_drop,
        )
        if any(value < 0 or value > 1 for value in drops):
            raise ValueError("maximum regression tolerances must be between 0 and 1")


@dataclass(frozen=True)
class EvaluationDecision:
    passed: bool
    run_id: str
    baseline_run_id: str | None
    reasons: tuple[str, ...]
    metrics: dict[str, float]
    comparison: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "run_id": self.run_id,
            "baseline_run_id": self.baseline_run_id,
            "reasons": list(self.reasons),
            "metrics": self.metrics,
            "comparison": self.comparison,
        }


class EvaluationControlPlane:
    """Deterministic gate over persisted evaluation runs."""

    def __init__(self, store: EvaluationIntelligenceStore) -> None:
        self.store = store

    @staticmethod
    def _metrics(report: dict[str, Any]) -> dict[str, float]:
        return {
            "pass_rate": float(report.get("pass_rate", 0)),
            "check_score": float(report.get("average_check_score", 0)),
            "grounding_score": float(report.get("average_grounding_score", 0)),
        }

    def gate(
        self,
        run_id: str,
        *,
        baseline_run_id: str | None = None,
        policy: EvaluationPolicy | None = None,
    ) -> EvaluationDecision:
        policy = policy or EvaluationPolicy()
        current = self.store.get_run(run_id)
        if current is None:
            raise KeyError(f"unknown evaluation run: {run_id}")
        baseline = self.store.get_run(baseline_run_id) if baseline_run_id else None
        if baseline_run_id and baseline is None:
            raise KeyError(f"unknown baseline evaluation run: {baseline_run_id}")
        if baseline and (current.suite_name, current.suite_version) != (
            baseline.suite_name,
            baseline.suite_version,
        ):
            raise ValueError("evaluation suites do not match")

        metrics = self._metrics(current.report)
        reasons: list[str] = []
        if metrics["pass_rate"] < policy.minimum_pass_rate:
            reasons.append("quality.pass_rate_below_threshold")
        if metrics["check_score"] < policy.minimum_check_score:
            reasons.append("quality.check_score_below_threshold")
        if metrics["grounding_score"] < policy.minimum_grounding_score:
            reasons.append("quality.grounding_score_below_threshold")

        comparison = None
        if baseline:
            comparison = compare_reports(baseline.report, current.report)
            deltas = comparison["deltas"]
            if deltas["pass_rate"] < -policy.maximum_pass_rate_drop:
                reasons.append("regression.pass_rate_drop_exceeded")
            if deltas["average_check_score"] < -policy.maximum_check_score_drop:
                reasons.append("regression.check_score_drop_exceeded")
            if deltas["average_grounding_score"] < -policy.maximum_grounding_score_drop:
                reasons.append("regression.grounding_score_drop_exceeded")

        return EvaluationDecision(
            passed=not reasons,
            run_id=run_id,
            baseline_run_id=baseline_run_id,
            reasons=tuple(reasons),
            metrics=metrics,
            comparison=comparison,
        )

    def quality_summary(self, *, suite_name: str | None = None, limit: int = 20) -> dict[str, Any]:
        runs = self.store.list_runs(suite_name, max(1, min(limit, 100)))
        if not runs:
            return {"status": "no-data", "runs": 0, "latest": None, "average": None}
        metrics = [self._metrics(item.report) for item in runs]
        average = {
            key: round(sum(item[key] for item in metrics) / len(metrics), 3)
            for key in metrics[0]
        }
        latest = metrics[0]
        return {
            "status": "ready",
            "runs": len(runs),
            "latest": latest,
            "average": average,
            "latest_run_id": runs[0].run_id,
            "latest_suite": {"name": runs[0].suite_name, "version": runs[0].suite_version},
        }
