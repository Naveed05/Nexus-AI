import pytest

from nexus.core.evaluation import EvaluationCase, EvaluationGate, EvaluationHarness
from nexus.core.verification import VerificationResult


def test_evaluation_report_scores_all_cases():
    cases = [
        EvaluationCase(
            case_id="basic-output",
            category="core",
            objective="Return a useful result.",
            expected_checks=("non_empty_output", "objective_present"),
        ),
        EvaluationCase(
            case_id="grounded-output",
            category="research",
            objective="Summarize evidence.",
            expected_checks=("grounded_research",),
        ),
    ]
    results = [
        VerificationResult(
            passed=True,
            checks={"non_empty_output": True, "objective_present": True},
        ),
        VerificationResult(
            passed=True,
            checks={"grounded_research": True},
            grounding_score=0.8,
        ),
    ]

    report = EvaluationHarness().report(cases, results)

    assert report.passed
    assert report.total_cases == 2
    assert report.passed_cases == 2
    assert report.pass_rate == 1.0
    assert report.average_check_score == 1.0
    assert report.average_grounding_score == 0.9
    assert report.as_dict()["scores"][1]["grounding_score"] == 0.8


def test_evaluation_report_marks_failed_case():
    case = EvaluationCase(
        case_id="failed-output",
        category="core",
        objective="Return a result.",
        expected_checks=("non_empty_output",),
    )
    result = VerificationResult(
        passed=False,
        checks={"non_empty_output": False},
        issues=("Model returned empty output.",),
    )

    report = EvaluationHarness().report([case], [result])

    assert not report.passed
    assert report.pass_rate == 0.0
    assert report.scores[0].issue_count == 1
    assert report.scores[0].check_score == 0.0


def test_evaluation_gate_enforces_explicit_thresholds():
    passing = EvaluationHarness().report(
        [EvaluationCase(case_id="one", category="core", objective="x")],
        [VerificationResult(passed=True, checks={})],
    )
    assert EvaluationGate(minimum_pass_rate=1.0, minimum_average_check_score=1.0).evaluate(passing)

    failing = EvaluationHarness().report(
        [EvaluationCase(case_id="one", category="core", objective="x")],
        [VerificationResult(passed=False, checks={})],
    )
    assert not EvaluationGate(minimum_pass_rate=1.0).evaluate(failing)


def test_evaluation_gate_rejects_invalid_thresholds():
    with pytest.raises(ValueError, match="between 0 and 1"):
        EvaluationGate(minimum_pass_rate=1.1)
    with pytest.raises(ValueError, match="between 0 and 1"):
        EvaluationGate(minimum_average_check_score=-0.1)


def test_evaluation_report_exposes_category_aggregates():
    cases = [
        EvaluationCase(case_id="a", category="core", objective="a"),
        EvaluationCase(case_id="b", category="core", objective="b"),
        EvaluationCase(case_id="c", category="research", objective="c"),
    ]
    results = [
        VerificationResult(passed=True, checks={}),
        VerificationResult(passed=False, checks={}),
        VerificationResult(passed=True, checks={}, grounding_score=0.6),
    ]
    report = EvaluationHarness().report(cases, results)
    categories = {item.category: item for item in report.by_category()}
    assert categories["core"].total_cases == 2
    assert categories["core"].pass_rate == 0.5
    assert categories["research"].average_grounding_score == 0.6
    assert len(report.as_dict()["categories"]) == 2


def test_evaluation_regression_detects_quality_drop():
    harness = EvaluationHarness()
    baseline = harness.report(
        [EvaluationCase(case_id="a", category="core", objective="a")],
        [VerificationResult(passed=True, checks={})],
    )
    current = harness.report(
        [EvaluationCase(case_id="a", category="core", objective="a")],
        [VerificationResult(passed=False, checks={})],
    )
    regression = harness.compare(baseline, current)
    assert regression.pass_rate_delta == -1.0
    assert regression.regressed


def test_evaluation_regression_allows_configured_tolerance():
    harness = EvaluationHarness()
    baseline = harness.report(
        [EvaluationCase(case_id="a", category="core", objective="a")],
        [VerificationResult(passed=True, checks={})],
    )
    current = harness.report(
        [EvaluationCase(case_id="a", category="core", objective="a")],
        [VerificationResult(passed=False, checks={})],
    )
    regression = harness.compare(
        baseline,
        current,
        maximum_pass_rate_drop=1.0,
        maximum_check_score_drop=1.0,
    )
    assert not regression.regressed


def test_evaluation_regression_rejects_negative_tolerances():
    report = EvaluationHarness().report(
        [EvaluationCase(case_id="a", category="core", objective="a")],
        [VerificationResult(passed=True, checks={})],
    )
    with pytest.raises(ValueError, match="cannot be negative"):
        EvaluationHarness.compare(report, report, maximum_pass_rate_drop=-0.1)


def test_evaluation_report_rejects_mismatched_inputs():
    with pytest.raises(ValueError, match="same length"):
        EvaluationHarness().report(
            [EvaluationCase(case_id="one", category="core", objective="x")],
            [],
        )


def test_evaluation_report_rejects_empty_suite():
    with pytest.raises(ValueError, match="at least one"):
        EvaluationHarness().report([], [])
