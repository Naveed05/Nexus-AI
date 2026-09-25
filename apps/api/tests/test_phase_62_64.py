from nexus.core.evaluation import EvaluationCase, EvaluationHarness
from nexus.core.evaluation_control import EvaluationControlPlane, EvaluationPolicy
from nexus.core.evaluation_intelligence import EvaluationIntelligenceStore
from nexus.core.reliability import ReliabilityStore
from nexus.core.verification import VerificationResult


def _save(store, run_id, passed, grounding=1.0):
    case = EvaluationCase(case_id="case-1", category="core", objective="x")
    report = EvaluationHarness().report(
        [case],
        [VerificationResult(passed=passed, checks={"objective": 1.0}, grounding_score=grounding)],
    )
    return store.save_run("suite", "1", report, run_id=run_id)


def test_phase_62_gate_enforces_absolute_quality_and_regression(tmp_path):
    store = EvaluationIntelligenceStore(tmp_path / "evaluation.sqlite3")
    _save(store, "baseline", True)
    _save(store, "current", False, grounding=0.5)
    decision = EvaluationControlPlane(store).gate(
        "current",
        baseline_run_id="baseline",
        policy=EvaluationPolicy(
            minimum_pass_rate=0.0,
            minimum_check_score=0.0,
            minimum_grounding_score=0.0,
            maximum_pass_rate_drop=0.5,
            maximum_check_score_drop=1.0,
            maximum_grounding_score_drop=0.1,
        ),
    )
    assert not decision.passed
    assert "regression.pass_rate_drop_exceeded" in decision.reasons
    assert "regression.grounding_score_drop_exceeded" in decision.reasons


def test_phase_62_gate_passes_within_tolerance(tmp_path):
    store = EvaluationIntelligenceStore(tmp_path / "evaluation.sqlite3")
    _save(store, "baseline", True)
    _save(store, "current", True, grounding=1.0)
    decision = EvaluationControlPlane(store).gate("current", baseline_run_id="baseline")
    assert decision.passed
    assert decision.metrics["pass_rate"] == 1.0


def test_phase_63_reliability_store_round_trip(tmp_path):
    store = ReliabilityStore(tmp_path / "reliability.sqlite3")
    saved = store.record("reconcile", "completed", {"recovered_jobs": 2})
    loaded = store.list()
    assert loaded[0].record_id == saved.record_id
    assert loaded[0].details["recovered_jobs"] == 2
