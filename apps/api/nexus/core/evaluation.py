from dataclasses import dataclass, field
from typing import Any

from nexus.core.verification import VerificationResult


@dataclass(frozen=True)
class EvaluationCase:
    """A deterministic benchmark case for a NEXUS capability."""

    case_id: str
    category: str
    objective: str
    expected_checks: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationScore:
    """Machine-readable score for one benchmark case."""

    case_id: str
    category: str
    passed: bool
    check_score: float
    grounding_score: float
    issue_count: int


@dataclass(frozen=True)
class CategoryEvaluation:
    """Aggregate observable quality for one benchmark category."""

    category: str
    total_cases: int
    passed_cases: int
    pass_rate: float
    average_check_score: float
    average_grounding_score: float


@dataclass(frozen=True)
class EvaluationRegression:
    """Deterministic comparison between a baseline and current report."""

    pass_rate_delta: float
    check_score_delta: float
    grounding_score_delta: float
    regressed: bool


@dataclass(frozen=True)
class EvaluationReport:
    """Aggregate benchmark report suitable for CI and future dashboards."""

    total_cases: int
    passed_cases: int
    pass_rate: float
    average_check_score: float
    average_grounding_score: float
    scores: tuple[EvaluationScore, ...]

    @property
    def passed(self) -> bool:
        return self.total_cases > 0 and self.passed_cases == self.total_cases

    def by_category(self) -> tuple[CategoryEvaluation, ...]:
        categories = sorted({score.category for score in self.scores})
        results: list[CategoryEvaluation] = []
        for category in categories:
            scores = tuple(score for score in self.scores if score.category == category)
            total = len(scores)
            passed = sum(score.passed for score in scores)
            results.append(
                CategoryEvaluation(
                    category=category,
                    total_cases=total,
                    passed_cases=passed,
                    pass_rate=round(passed / total, 3),
                    average_check_score=round(sum(score.check_score for score in scores) / total, 3),
                    average_grounding_score=round(sum(score.grounding_score for score in scores) / total, 3),
                )
            )
        return tuple(results)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "pass_rate": self.pass_rate,
            "average_check_score": self.average_check_score,
            "average_grounding_score": self.average_grounding_score,
            "passed": self.passed,
            "categories": [
                {
                    "category": category.category,
                    "total_cases": category.total_cases,
                    "passed_cases": category.passed_cases,
                    "pass_rate": category.pass_rate,
                    "average_check_score": category.average_check_score,
                    "average_grounding_score": category.average_grounding_score,
                }
                for category in self.by_category()
            ],
            "scores": [
                {
                    "case_id": score.case_id,
                    "category": score.category,
                    "passed": score.passed,
                    "check_score": score.check_score,
                    "grounding_score": score.grounding_score,
                    "issue_count": score.issue_count,
                }
                for score in self.scores
            ],
        }


@dataclass(frozen=True)
class EvaluationGate:
    """Explicit quality thresholds for deciding whether a report passes CI."""

    minimum_pass_rate: float = 1.0
    minimum_average_check_score: float = 1.0
    minimum_average_grounding_score: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("minimum_pass_rate", self.minimum_pass_rate),
            ("minimum_average_check_score", self.minimum_average_check_score),
            ("minimum_average_grounding_score", self.minimum_average_grounding_score),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")

    def evaluate(self, report: EvaluationReport) -> bool:
        return (
            report.pass_rate >= self.minimum_pass_rate
            and report.average_check_score >= self.minimum_average_check_score
            and report.average_grounding_score >= self.minimum_average_grounding_score
        )


class EvaluationHarness:
    """Runs deterministic evaluations against NEXUS verification results.

    This intentionally evaluates observable behavior rather than hidden model
    reasoning, making it safe to run in CI and compare across model versions.
    """

    def evaluate_case(
        self,
        case: EvaluationCase,
        verification: VerificationResult,
    ) -> EvaluationScore:
        expected = case.expected_checks or tuple(verification.checks)
        if expected:
            passed_checks = sum(bool(verification.checks.get(name)) for name in expected)
            check_score = round(passed_checks / len(expected), 3)
        else:
            check_score = 1.0 if verification.passed else 0.0

        return EvaluationScore(
            case_id=case.case_id,
            category=case.category,
            passed=verification.passed and check_score == 1.0,
            check_score=check_score,
            grounding_score=round(verification.grounding_score, 3),
            issue_count=len(verification.issues),
        )

    def report(
        self,
        cases: list[EvaluationCase],
        results: list[VerificationResult],
    ) -> EvaluationReport:
        if len(cases) != len(results):
            raise ValueError("cases and results must have the same length")
        if not cases:
            raise ValueError("at least one evaluation case is required")

        scores = tuple(
            self.evaluate_case(case, result)
            for case, result in zip(cases, results)
        )
        total = len(scores)
        passed = sum(score.passed for score in scores)
        return EvaluationReport(
            total_cases=total,
            passed_cases=passed,
            pass_rate=round(passed / total, 3),
            average_check_score=round(
                sum(score.check_score for score in scores) / total,
                3,
            ),
            average_grounding_score=round(
                sum(score.grounding_score for score in scores) / total,
                3,
            ),
            scores=scores,
        )

    @staticmethod
    def compare(
        baseline: EvaluationReport,
        current: EvaluationReport,
        *,
        maximum_pass_rate_drop: float = 0.0,
        maximum_check_score_drop: float = 0.0,
        maximum_grounding_score_drop: float = 1.0,
    ) -> EvaluationRegression:
        for name, value in (
            ("maximum_pass_rate_drop", maximum_pass_rate_drop),
            ("maximum_check_score_drop", maximum_check_score_drop),
            ("maximum_grounding_score_drop", maximum_grounding_score_drop),
        ):
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
        pass_delta = round(current.pass_rate - baseline.pass_rate, 3)
        check_delta = round(current.average_check_score - baseline.average_check_score, 3)
        grounding_delta = round(current.average_grounding_score - baseline.average_grounding_score, 3)
        regressed = (
            pass_delta < -maximum_pass_rate_drop
            or check_delta < -maximum_check_score_drop
            or grounding_delta < -maximum_grounding_score_drop
        )
        return EvaluationRegression(pass_delta, check_delta, grounding_delta, regressed)
