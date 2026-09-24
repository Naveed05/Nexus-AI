import json

import pytest

from nexus.core.evaluation import EvaluationCase, EvaluationHarness
from nexus.core.evaluation_intelligence import (
    EvaluationIntelligenceStore,
    compare_reports,
    telemetry_event,
)
from nexus.core.verification import VerificationResult


def _report(passed: bool = True):
    case = EvaluationCase(case_id="case-1", category="core", objective="x")
    return EvaluationHarness().report([case], [VerificationResult(passed=passed, checks={})])


def test_evaluation_intelligence_persists_runs_and_lists(tmp_path):
    store = EvaluationIntelligenceStore(tmp_path / "evaluation.sqlite3")
    report = _report()
    saved = store.save_run("core", "1", report, {"model_id": "test-model"})
    loaded = store.get_run(saved.run_id)
    assert loaded is not None
    assert loaded.report["pass_rate"] == 1.0
    assert loaded.metadata["model_id"] == "test-model"
    assert [item.run_id for item in store.list_runs()] == [saved.run_id]


def test_compare_reports_identifies_case_regression_and_recovery():
    baseline = _report(True).as_dict()
    current = _report(False).as_dict()
    comparison = compare_reports(baseline, current)
    assert comparison["regressed"]
    assert comparison["deltas"]["pass_rate"] == -1.0
    assert comparison["failed_case_ids"] == ["case-1"]


def test_telemetry_metrics_aggregate_quality_cost_and_latency(tmp_path):
    store = EvaluationIntelligenceStore(tmp_path / "evaluation.sqlite3")
    store.save_telemetry(telemetry_event("model", "gpt-test", latency_ms=100, tokens=100, cost_usd=0.01, quality_score=0.9))
    store.save_telemetry(telemetry_event("model", "gpt-test", success=False, latency_ms=200, tokens=50, cost_usd=0.02, quality_score=0.5))
    metrics = store.component_metrics("model")
    assert metrics[0]["events"] == 2
    assert metrics[0]["success_rate"] == 0.5
    assert metrics[0]["average_latency_ms"] == 150.0
    assert metrics[0]["total_tokens"] == 150
    assert metrics[0]["total_cost_usd"] == 0.03
    assert metrics[0]["average_quality_score"] == 0.7


def test_telemetry_rejects_invalid_numbers(tmp_path):
    store = EvaluationIntelligenceStore(tmp_path / "evaluation.sqlite3")
    with pytest.raises(ValueError, match="cannot be negative"):
        store.save_telemetry(telemetry_event("model", "x", latency_ms=-1))


def test_api_evaluation_control_plane():
    from nexus.api.main import client
    report = _report().as_dict()
    created = client.post("/api/v1/evaluations/runs", json={
        "suite_name": "api-suite", "suite_version": "1", "report": report,
        "metadata": {"agent_id": "planner"},
    })
    assert created.status_code == 201
    run_id = created.json()["run_id"]
    fetched = client.get(f"/api/v1/evaluations/runs/{run_id}")
    assert fetched.status_code == 200
    assert fetched.json()["metadata"]["agent_id"] == "planner"
    telemetry = client.post("/api/v1/evaluations/telemetry", json={
        "component_type": "agent", "component_id": "planner",
        "latency_ms": 42, "tokens": 20, "cost_usd": 0.001, "quality_score": 1.0,
    })
    assert telemetry.status_code == 201
    metrics = client.get("/api/v1/evaluations/metrics?component_type=agent")
    assert metrics.status_code == 200
    assert metrics.json()[0]["component_id"] == "planner"
