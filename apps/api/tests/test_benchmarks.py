import pytest

from nexus.core.benchmarks import BenchmarkRunner, BenchmarkSuite, compare_benchmarks
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
