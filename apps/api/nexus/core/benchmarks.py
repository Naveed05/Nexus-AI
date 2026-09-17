import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from nexus.core.evaluation import EvaluationCase, EvaluationGate, EvaluationReport, EvaluationRegression
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

    @property
    def fingerprint(self) -> str:
        """Return a stable SHA-256 identity for the exact benchmark definition."""
        payload = json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class BenchmarkRunner:
    """Executes a benchmark suite while preserving suite ordering and identity."""

    def __init__(self, evaluator: Callable[[EvaluationCase], VerificationResult]) -> None:
        self._evaluator = evaluator

    def run(self, suite: BenchmarkSuite) -> EvaluationReport:
        cases = list(suite.ordered_cases())
        results = [self._evaluator(case) for case in cases]
        from nexus.core.evaluation import EvaluationHarness

        return EvaluationHarness().report(cases, results)



def _stable_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _report_from_dict(payload: dict[str, Any]) -> EvaluationReport:
    """Rehydrate a report from its safe JSON-compatible representation."""
    if not isinstance(payload, dict):
        raise ValueError("benchmark report must be an object")
    scores_payload = payload.get("scores")
    if not isinstance(scores_payload, list) or not scores_payload:
        raise ValueError("benchmark report must contain scores")

    try:
        scores = tuple(
            __import__("nexus.core.evaluation", fromlist=["EvaluationScore"]).EvaluationScore(
                case_id=item["case_id"],
                category=item["category"],
                passed=item["passed"],
                check_score=item["check_score"],
                grounding_score=item["grounding_score"],
                issue_count=item["issue_count"],
            )
            for item in scores_payload
        )
        report = EvaluationReport(
            total_cases=payload["total_cases"],
            passed_cases=payload["passed_cases"],
            pass_rate=payload["pass_rate"],
            average_check_score=payload["average_check_score"],
            average_grounding_score=payload["average_grounding_score"],
            scores=scores,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid benchmark report payload") from exc

    if report.as_dict() != payload:
        raise ValueError("benchmark report payload is inconsistent")
    return report


@dataclass(frozen=True)
class BenchmarkBaseline:
    """Immutable baseline bound to an exact benchmark suite and report identity."""

    suite_name: str
    suite_version: str
    case_ids: tuple[str, ...]
    report: EvaluationReport
    suite_fingerprint: str = ""
    report_fingerprint: str = ""

    @classmethod
    def from_suite(cls, suite: BenchmarkSuite, report: EvaluationReport) -> "BenchmarkBaseline":
        expected_ids = tuple(case.case_id for case in suite.ordered_cases())
        actual_ids = tuple(score.case_id for score in report.scores)
        if actual_ids != expected_ids:
            raise ValueError("baseline report does not match benchmark suite")
        return cls(
            suite.name,
            suite.version,
            expected_ids,
            report,
            suite.fingerprint,
            _stable_fingerprint(report.as_dict()),
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BenchmarkBaseline":
        """Safely restore a persisted baseline without arbitrary object deserialization."""
        if not isinstance(payload, dict):
            raise ValueError("benchmark baseline must be an object")
        try:
            case_ids = tuple(payload["case_ids"])
            baseline = cls(
                suite_name=payload["suite_name"],
                suite_version=payload["suite_version"],
                case_ids=case_ids,
                report=_report_from_dict(payload["report"]),
                suite_fingerprint=payload["suite_fingerprint"],
                report_fingerprint=payload["report_fingerprint"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid benchmark baseline payload") from exc
        if baseline.report_fingerprint != _stable_fingerprint(baseline.report.as_dict()):
            raise ValueError("baseline report fingerprint does not match stored report")
        if tuple(score.case_id for score in baseline.report.scores) != baseline.case_ids:
            raise ValueError("baseline case identities do not match stored report")
        return baseline

    @classmethod
    def from_json(cls, payload: str) -> "BenchmarkBaseline":
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid benchmark baseline JSON") from exc
        return cls.from_dict(decoded)

    def validate_for(self, suite: BenchmarkSuite, report: EvaluationReport) -> None:
        if self.suite_name != suite.name or self.suite_version != suite.version:
            raise ValueError("baseline benchmark identity does not match suite")
        if self.suite_fingerprint and self.suite_fingerprint != suite.fingerprint:
            raise ValueError("baseline benchmark fingerprint does not match suite")
        if self.report_fingerprint and self.report_fingerprint != _stable_fingerprint(self.report.as_dict()):
            raise ValueError("baseline report fingerprint does not match stored report")
        expected_ids = tuple(case.case_id for case in suite.ordered_cases())
        actual_ids = tuple(score.case_id for score in report.scores)
        if self.case_ids != expected_ids or actual_ids != expected_ids:
            raise ValueError("benchmark case identities do not match baseline")

    def as_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "suite_version": self.suite_version,
            "suite_fingerprint": self.suite_fingerprint,
            "report_fingerprint": self.report_fingerprint,
            "case_ids": list(self.case_ids),
            "report": self.report.as_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class BenchmarkComparison:
    """A named comparison between two benchmark reports with actionable diagnostics."""

    suite_name: str
    suite_version: str
    regression: EvaluationRegression
    failed_case_ids: tuple[str, ...] = ()
    recovered_case_ids: tuple[str, ...] = ()

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
            "diagnostics": {
                "failed_case_ids": list(self.failed_case_ids),
                "recovered_case_ids": list(self.recovered_case_ids),
            },
        }


@dataclass(frozen=True)
class BenchmarkGateResult:
    """Machine-readable result of absolute quality and regression gates."""

    comparison: BenchmarkComparison
    quality_passed: bool
    failure_reasons: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.quality_passed and not self.comparison.regressed

    def as_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.comparison.suite_name,
            "suite_version": self.comparison.suite_version,
            "quality_passed": self.quality_passed,
            "regression_passed": not self.comparison.regressed,
            "passed": self.passed,
            "failure_reasons": list(self.failure_reasons),
            "comparison": self.comparison.as_dict(),
        }


class BenchmarkGate:
    """Combines absolute quality thresholds with baseline regression protection."""

    def __init__(
        self,
        quality_gate: EvaluationGate | None = None,
        *,
        maximum_pass_rate_drop: float = 0.0,
        maximum_check_score_drop: float = 0.0,
        maximum_grounding_score_drop: float = 1.0,
    ) -> None:
        self._quality_gate = quality_gate or EvaluationGate()
        self._maximum_pass_rate_drop = maximum_pass_rate_drop
        self._maximum_check_score_drop = maximum_check_score_drop
        self._maximum_grounding_score_drop = maximum_grounding_score_drop

    def evaluate(
        self,
        suite: BenchmarkSuite,
        baseline: EvaluationReport,
        current: EvaluationReport,
    ) -> BenchmarkGateResult:
        comparison = compare_benchmarks(
            suite,
            baseline,
            current,
            maximum_pass_rate_drop=self._maximum_pass_rate_drop,
            maximum_check_score_drop=self._maximum_check_score_drop,
            maximum_grounding_score_drop=self._maximum_grounding_score_drop,
        )
        quality_passed = self._quality_gate.evaluate(current)
        reasons: list[str] = []
        if current.pass_rate < self._quality_gate.minimum_pass_rate:
            reasons.append("quality.pass_rate_below_threshold")
        if current.average_check_score < self._quality_gate.minimum_average_check_score:
            reasons.append("quality.average_check_score_below_threshold")
        if current.average_grounding_score < self._quality_gate.minimum_average_grounding_score:
            reasons.append("quality.average_grounding_score_below_threshold")
        if comparison.regression.pass_rate_delta < -self._maximum_pass_rate_drop:
            reasons.append("regression.pass_rate_drop_exceeded")
        if comparison.regression.check_score_delta < -self._maximum_check_score_drop:
            reasons.append("regression.check_score_drop_exceeded")
        if comparison.regression.grounding_score_delta < -self._maximum_grounding_score_drop:
            reasons.append("regression.grounding_score_drop_exceeded")
        return BenchmarkGateResult(comparison, quality_passed, tuple(reasons))


def compare_benchmarks(
    suite: BenchmarkSuite,
    baseline: EvaluationReport,
    current: EvaluationReport,
    *,
    maximum_pass_rate_drop: float = 0.0,
    maximum_check_score_drop: float = 0.0,
    maximum_grounding_score_drop: float = 1.0,
) -> BenchmarkComparison:
    """Compare reports and retain benchmark identity plus case-level diagnostics."""
    benchmark_baseline = BenchmarkBaseline.from_suite(suite, baseline)
    benchmark_baseline.validate_for(suite, current)

    from nexus.core.evaluation import EvaluationHarness

    regression = EvaluationHarness.compare(
        baseline,
        current,
        maximum_pass_rate_drop=maximum_pass_rate_drop,
        maximum_check_score_drop=maximum_check_score_drop,
        maximum_grounding_score_drop=maximum_grounding_score_drop,
    )
    baseline_by_id = {score.case_id: score for score in baseline.scores}
    current_by_id = {score.case_id: score for score in current.scores}
    failed_case_ids = tuple(
        case_id
        for case_id in sorted(baseline_by_id)
        if baseline_by_id[case_id].passed and not current_by_id[case_id].passed
    )
    recovered_case_ids = tuple(
        case_id
        for case_id in sorted(baseline_by_id)
        if not baseline_by_id[case_id].passed and current_by_id[case_id].passed
    )
    return BenchmarkComparison(
        suite.name,
        suite.version,
        regression,
        failed_case_ids,
        recovered_case_ids,
    )
