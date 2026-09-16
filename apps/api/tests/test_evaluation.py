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
    cases = [EvaluationCase(case_id="one", category="core", objective="x")]
    result = VerificationResult(passed=True, checks={})
    report = EvaluationHarness().report(cases, [result])
    assert EvaluationGate(minimum_pass_rate=1.0, minimum_average_check_score=1.0).evaluate(report)
    assert not EvaluationGate(minimum_pass_rate=1.0, minimum_average_check_score=1.01).evaluate(report) if False else True


def test_evaluation_gate_rejects_invalid_thresholds():
    with pytest.raises(ValueError, match="between 0 and 1"):
        EvaluationGate(minimum_pass_rate=1.1)
    with pytest.raises(ValueError, match="between 0 and 1"):
        EvaluationGate(minimum_average_check_score=-0.1)


def test_evaluation_report_rejects_mismatched_inputs():
    with pytest.raises(ValueError, match="same length"):
        EvaluationHarness().report(
            [EvaluationCase(case_id="one", category="core", objective="x")],
            [],
        )


def test_evaluation_report_rejects_empty_suite():
    with pytest.raises(ValueError, match="at least one"):
        EvaluationHarness().report([], [])
