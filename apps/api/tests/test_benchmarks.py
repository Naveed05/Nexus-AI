import pytest

from nexus.core.benchmarks import BenchmarkBaseline, BenchmarkRunner, BenchmarkSuite, compare_benchmarks
from nexus.core.evaluation import EvaluationCase
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


def test_benchmark_baseline_carries_suite_fingerprint():
    suite = BenchmarkSuite(
        name="core",
        version="1",
        cases=(EvaluationCase(case_id="a", category="core", objective="a"),),
    )
    report = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(suite)
    baseline = BenchmarkBaseline.from_suite(suite, report)

    assert baseline.suite_fingerprint == suite.fingerprint
    assert baseline.as_dict()["suite_fingerprint"] == suite.fingerprint


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
