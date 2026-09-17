import pytest

from nexus.core.benchmarks import (
    BenchmarkBaseline,
    BenchmarkGate,
    BenchmarkRunner,
    BenchmarkSuite,
    compare_benchmarks,
)
from nexus.core.evaluation import EvaluationCase, EvaluationGate
from nexus.core.verification import VerificationResult


def test_benchmark_suite_orders_cases_deterministically():
    suite = BenchmarkSuite(
        name="core",
        version="1",
        cases=(
            EvaluationCase(case_id="b", category="research", objective="b"),
            EvaluationCase(case_id="a", category="core", objective="a"),
        ),
    )

    assert suite.case_ids == ("b", "a")
    assert [case.case_id for case in suite.ordered_cases()] == ["a", "b"]
    assert [case["case_id"] for case in suite.as_dict()["cases"]] == ["a", "b"]


def test_benchmark_suite_rejects_duplicate_ids():
    case = EvaluationCase(case_id="same", category="core", objective="x")
    with pytest.raises(ValueError, match="must be unique"):
        BenchmarkSuite(name="core", version="1", cases=(case, case))


def test_benchmark_runner_uses_suite_order():
    seen = []

    def evaluate(case):
        seen.append(case.case_id)
        return VerificationResult(passed=True, checks={})

    suite = BenchmarkSuite(
        name="core",
        version="1",
        cases=(
            EvaluationCase(case_id="z", category="core", objective="z"),
            EvaluationCase(case_id="a", category="core", objective="a"),
        ),
    )

    report = BenchmarkRunner(evaluate).run(suite)

    assert seen == ["a", "z"]
    assert report.passed
    assert [score.case_id for score in report.scores] == ["a", "z"]


def test_benchmark_fingerprint_is_deterministic_and_definition_bound():
    cases = (
        EvaluationCase(case_id="b", category="research", objective="b"),
        EvaluationCase(case_id="a", category="core", objective="a"),
    )
    first = BenchmarkSuite(name="core", version="1", cases=cases)
    reordered = BenchmarkSuite(name="core", version="1", cases=tuple(reversed(cases)))
    changed = BenchmarkSuite(
        name="core", version="1", cases=(cases[0], EvaluationCase(case_id="a", category="core", objective="changed"))
    )

    assert first.fingerprint == reordered.fingerprint
    assert first.fingerprint != changed.fingerprint


def test_benchmark_baseline_carries_suite_and_report_fingerprints():
    suite = BenchmarkSuite(
        name="core",
        version="1",
        cases=(EvaluationCase(case_id="a", category="core", objective="a"),),
    )
    report = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(suite)
    baseline = BenchmarkBaseline.from_suite(suite, report)

    assert baseline.suite_fingerprint == suite.fingerprint
    assert baseline.report_fingerprint
    assert baseline.as_dict()["suite_fingerprint"] == suite.fingerprint
    assert baseline.as_dict()["report_fingerprint"] == baseline.report_fingerprint


def test_benchmark_baseline_rejects_tampered_stored_report():
    suite = BenchmarkSuite(
        name="core",
        version="1",
        cases=(EvaluationCase(case_id="a", category="core", objective="a"),),
    )
    report = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(suite)
    baseline = BenchmarkBaseline.from_suite(suite, report)
    tampered = BenchmarkBaseline(
        baseline.suite_name,
        baseline.suite_version,
        baseline.case_ids,
        BenchmarkRunner(lambda _: VerificationResult(passed=False, checks={})).run(suite),
        baseline.suite_fingerprint,
        baseline.report_fingerprint,
    )

    with pytest.raises(ValueError, match="report fingerprint does not match"):
        tampered.validate_for(suite, report)


def test_compare_benchmarks_preserves_suite_identity():
    suite = BenchmarkSuite(
        name="core",
        version="2026.1",
        cases=(EvaluationCase(case_id="a", category="core", objective="a"),),
    )
    baseline = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(suite)
    current = BenchmarkRunner(lambda _: VerificationResult(passed=False, checks={})).run(suite)

    comparison = compare_benchmarks(suite, baseline, current)

    assert comparison.suite_name == "core"
    assert comparison.suite_version == "2026.1"
    assert comparison.regressed
    assert comparison.as_dict()["regression"]["pass_rate_delta"] == -1.0
    assert comparison.failed_case_ids == ("a",)
    assert comparison.recovered_case_ids == ()
    assert comparison.as_dict()["diagnostics"]["failed_case_ids"] == ["a"]


def test_compare_benchmarks_reports_recovered_cases():
    suite = BenchmarkSuite(
        name="core",
        version="1",
        cases=(
            EvaluationCase(case_id="a", category="core", objective="a"),
            EvaluationCase(case_id="b", category="core", objective="b"),
        ),
    )
    baseline = BenchmarkRunner(
        lambda case: VerificationResult(passed=case.case_id == "a", checks={})
    ).run(suite)
    current = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(suite)

    comparison = compare_benchmarks(suite, baseline, current)

    assert comparison.failed_case_ids == ()
    assert comparison.recovered_case_ids == ("b",)


def test_benchmark_baseline_rejects_report_from_different_suite():
    suite = BenchmarkSuite(
        name="core",
        version="1",
        cases=(EvaluationCase(case_id="a", category="core", objective="a"),),
    )
    other_suite = BenchmarkSuite(
        name="core",
        version="2",
        cases=(EvaluationCase(case_id="a", category="core", objective="a"),),
    )
    report = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(suite)
    other_report = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(other_suite)
    baseline = BenchmarkBaseline.from_suite(suite, report)

    with pytest.raises(ValueError, match="identity does not match"):
        baseline.validate_for(other_suite, other_report)


def test_benchmark_baseline_rejects_definition_fingerprint_mismatch():
    suite = BenchmarkSuite(
        name="core",
        version="1",
        cases=(EvaluationCase(case_id="a", category="core", objective="a"),),
    )
    changed_suite = BenchmarkSuite(
        name="core",
        version="1",
        cases=(EvaluationCase(case_id="a", category="core", objective="changed"),),
    )
    report = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(suite)
    changed_report = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(changed_suite)
    baseline = BenchmarkBaseline.from_suite(suite, report)

    with pytest.raises(ValueError, match="fingerprint does not match"):
        baseline.validate_for(changed_suite, changed_report)


def test_benchmark_gate_requires_absolute_quality_and_no_regression():
    suite = BenchmarkSuite(
        name="core",
        version="1",
        cases=(EvaluationCase(case_id="a", category="core", objective="a"),),
    )
    baseline = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(suite)
    current = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(suite)

    result = BenchmarkGate().evaluate(suite, baseline, current)

    assert result.passed
    assert result.quality_passed
    assert result.as_dict()["regression_passed"]


def test_benchmark_gate_reports_absolute_quality_failure():
    suite = BenchmarkSuite(
        name="core",
        version="1",
        cases=(EvaluationCase(case_id="a", category="core", objective="a"),),
    )
    baseline = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(suite)
    current = BenchmarkRunner(lambda _: VerificationResult(passed=False, checks={})).run(suite)

    result = BenchmarkGate(
        quality_gate=EvaluationGate(minimum_pass_rate=0.0, minimum_average_check_score=0.0)
    ).evaluate(suite, baseline, current)

    assert not result.passed
    assert result.quality_passed
    assert result.comparison.regressed


def test_benchmark_gate_allows_configured_regression_tolerance():
    suite = BenchmarkSuite(
        name="core",
        version="1",
        cases=(EvaluationCase(case_id="a", category="core", objective="a"),),
    )
    baseline = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(suite)
    current = BenchmarkRunner(lambda _: VerificationResult(passed=False, checks={})).run(suite)

    result = BenchmarkGate(
        quality_gate=EvaluationGate(minimum_pass_rate=0.0, minimum_average_check_score=0.0),
        maximum_pass_rate_drop=1.0,
        maximum_check_score_drop=1.0,
    ).evaluate(suite, baseline, current)

    assert result.passed
    assert not result.comparison.regressed


def test_compare_benchmarks_rejects_case_identity_mismatch():
    suite = BenchmarkSuite(
        name="core",
        version="1",
        cases=(EvaluationCase(case_id="a", category="core", objective="a"),),
    )
    baseline = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(suite)
    mismatched = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(
        BenchmarkSuite(
            name="core",
            version="1",
            cases=(EvaluationCase(case_id="b", category="core", objective="b"),),
        )
    )

    with pytest.raises(ValueError, match="case identities do not match baseline"):
        compare_benchmarks(suite, baseline, mismatched)
