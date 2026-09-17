import hashlib
import json

import pytest

from nexus.core.benchmark_store import BenchmarkBaselineStore
from nexus.core.benchmarks import BenchmarkBaseline, BenchmarkRunner, BenchmarkSuite
from nexus.core.evaluation import EvaluationCase
from nexus.core.verification import VerificationResult


def _baseline():
    suite = BenchmarkSuite(
        name="core",
        version="1",
        cases=(EvaluationCase(case_id="a", category="core", objective="a"),),
    )
    report = BenchmarkRunner(lambda _: VerificationResult(passed=True, checks={})).run(suite)
    return BenchmarkBaseline.from_suite(suite, report)


def test_store_round_trips_baseline(tmp_path):
    store = BenchmarkBaselineStore(tmp_path)
    baseline = _baseline()

    store.save("core-v1", baseline)

    assert store.exists("core-v1")
    assert store.load("core-v1") == baseline


def test_store_writes_deterministic_json(tmp_path):
    store = BenchmarkBaselineStore(tmp_path)
    baseline = _baseline()

    store.save("core-v1", baseline)
    first = (tmp_path / "core-v1.json").read_text(encoding="utf-8")
    store.save("core-v1", baseline)
    second = (tmp_path / "core-v1.json").read_text(encoding="utf-8")

    assert first == second
    envelope = json.loads(first)
    canonical = json.dumps(envelope["baseline"], sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert envelope["integrity"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_store_rejects_tampered_payload(tmp_path):
    store = BenchmarkBaselineStore(tmp_path)
    store.save("core-v1", _baseline())
    path = tmp_path / "core-v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["baseline"]["suite_version"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="integrity check failed"):
        store.load("core-v1")


def test_store_rejects_unknown_schema(tmp_path):
    path = tmp_path / "core-v1.json"
    path.write_text(json.dumps({"schema": "future", "baseline": {}, "integrity": "x"}), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported benchmark baseline store schema"):
        BenchmarkBaselineStore(tmp_path).load("core-v1")


def test_store_rejects_invalid_keys(tmp_path):
    store = BenchmarkBaselineStore(tmp_path)
    with pytest.raises(ValueError, match="invalid benchmark baseline key"):
        store.save("../escape", _baseline())


def test_store_missing_baseline_is_explicit(tmp_path):
    with pytest.raises(FileNotFoundError, match="benchmark baseline not found"):
        BenchmarkBaselineStore(tmp_path).load("missing")


def test_store_delete_is_explicit(tmp_path):
    store = BenchmarkBaselineStore(tmp_path)
    store.save("core-v1", _baseline())
    store.delete("core-v1")

    assert not store.exists("core-v1")
    with pytest.raises(FileNotFoundError):
        store.delete("core-v1")
