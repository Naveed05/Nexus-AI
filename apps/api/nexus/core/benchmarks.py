from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from nexus.core.evaluation import EvaluationCase, EvaluationReport, EvaluationRegression
from nexus.core.verification import VerificationResult


@dataclass(frozen=True)
class BenchmarkSuite:
    """Validated, deterministically ordered collection of evaluation cases."""

    name: str
    version: str
    cases: tuple[EvaluationCase, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("benchmark name cannot be empty")
        if not self.version.strip():
            raise ValueError("benchmark version cannot be empty")
        if not self.cases:
            raise ValueError("benchmark suite must contain at least one case")

        ids = [case.case_id for case in self.cases]
        if any(not case_id.strip() for case_id in ids):
            raise ValueError("benchmark case ids cannot be empty")
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark case ids must be unique")

        categories = [case.category for case in self.cases]
        if any(not category.strip() for category in categories):
            raise ValueError("benchmark case categories cannot be empty")

    @property
    def case_ids(self) -> tuple[str, ...]:
        return tuple(case.case_id for case in self.cases)

    def ordered_cases(self) -> tuple[EvaluationCase, ...]:
        """Return a stable case order independent of input construction order."""
        return tuple(sorted(self.cases, key=lambda case: (case.category, case.case_id)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "metadata": dict(self.metadata),
            "cases": [
                {
                    "case_id": case.case_id,
                    "category": case.category,
                    "objective": case.objective,
                    "expected_checks": list(case.expected_checks),
                    "metadata": dict(case.metadata),
                }
                for case in self.ordered_cases()
            ],
        }


class BenchmarkRunner:
    """Executes a benchmark suite while preserving suite ordering and identity."""

    def __init__(self, evaluator: Callable[[EvaluationCase], VerificationResult]) -> None:
        self._evaluator = evaluator

    def run(self, suite: BenchmarkSuite) -> EvaluationReport:
        cases = list(suite.ordered_cases())
        results = [self._evaluator(case) for case in cases]
        from nexus.core.evaluation import EvaluationHarness

        return EvaluationHarness().report(cases, results)


@dataclass(frozen=True)
class BenchmarkComparison:
    """A named comparison between two benchmark reports."""

    suite_name: str
    suite_version: str
    regression: EvaluationRegression

    @property
    def regressed(self) -> bool:
        return self.regression.regressed

    def as_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "suite_version": self.suite_version,
            "regression": {
                "pass_rate_delta": self.regression.pass_rate_delta,
                "check_score_delta": self.regression.check_score_delta,
                "grounding_score_delta": self.regression.grounding_score_delta,
                "regressed": self.regression.regressed,
            },
        }


def compare_benchmarks(
    suite: BenchmarkSuite,
    baseline: EvaluationReport,
    current: EvaluationReport,
    *,
    maximum_pass_rate_drop: float = 0.0,
    maximum_check_score_drop: float = 0.0,
    maximum_grounding_score_drop: float = 1.0,
) -> BenchmarkComparison:
    """Compare reports and retain the benchmark identity in the result."""
    from nexus.core.evaluation import EvaluationHarness

    regression = EvaluationHarness.compare(
        baseline,
        current,
        maximum_pass_rate_drop=maximum_pass_rate_drop,
        maximum_check_score_drop=maximum_check_score_drop,
        maximum_grounding_score_drop=maximum_grounding_score_drop,
    )
    return BenchmarkComparison(suite.name, suite.version, regression)
