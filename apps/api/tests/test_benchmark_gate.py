import pytest

from nexus.core.benchmark_gate import evaluate_persisted_baseline, evaluate_persisted_baseline_path
from nexus.core.benchmark_store import BenchmarkBaselineStore
from nexus.core.benchmarks import BenchmarkBaseline, BenchmarkGate, BenchmarkRunner, BenchmarkSuite
from nexus.core.evaluation import EvaluationCase, EvaluationGate
from nexus.core.verification import VerificationResult


def _suite():
    return BenchmarkSuite(
        name="core",
        version="1",
        cases=(EvaluationCase(case_id="a", category="core", objective="a"),),
    )


def _report(suite, passed=True):
    return BenchmarkRunner(lambda _: VerificationResult(passed=passed, checks={})).run(suite)


def test_persisted_baseline_gate_passes(tmp_path):
    suite = _suite()
    baseline = BenchmarkBaseline.from_suite(suite, _report(suite, True))
    store = BenchmarkBaselineStore(tmp_path)
    store.save("core", baseline)

    result = evaluate_persisted_baseline(suite, _report(suite, True), store=store, baseline_key="core")

    assert result.passed
    assert result.failure_reasons == ()


def test_persisted_baseline_gate_surfaces_regression(tmp_path):
    suite = _suite()
    store = BenchmarkBaselineStore(tmp_path)
    store.save("core", BenchmarkBaseline.from_suite(suite, _report(suite, True)))

    result = evaluate_persisted_baseline(
        suite,
        _report(suite, False),
        store=store,
        baseline_key="core",
        gate=BenchmarkGate(
            quality_gate=EvaluationGate(minimum_pass_rate=0.0, minimum_average_check_score=0.0)
        ),
    )

    assert not result.passed
    assert "regression.pass_rate_drop_exceeded" in result.failure_reasons


def test_persisted_baseline_path_entry_point(tmp_path):
    suite = _suite()
    store = BenchmarkBaselineStore(tmp_path)
    store.save("core", BenchmarkBaseline.from_suite(suite, _report(suite, True)))

    result = evaluate_persisted_baseline_path(
        suite, _report(suite, True), store_path=tmp_path, baseline_key="core"
    )

    assert result.passed


def test_persisted_baseline_gate_rejects_tampered_store(tmp_path):
    suite = _suite()
    store = BenchmarkBaselineStore(tmp_path)
    store.save("core", BenchmarkBaseline.from_suite(suite, _report(suite, True)))
    path = tmp_path / "core.json"
    payload = path.read_text(encoding="utf-8").replace('"suite_version":"1"', '"suite_version":"2"')
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="integrity check failed"):
        evaluate_persisted_baseline(suite, _report(suite, True), store=store, baseline_key="core")
