"""Integration helpers for enforcing benchmark gates from durable baselines."""

from __future__ import annotations

from pathlib import Path

from nexus.core.benchmark_store import BenchmarkBaselineStore
from nexus.core.benchmarks import BenchmarkGate, BenchmarkGateResult, BenchmarkSuite
from nexus.core.evaluation import EvaluationReport


def evaluate_persisted_baseline(
    suite: BenchmarkSuite,
    current: EvaluationReport,
    *,
    store: BenchmarkBaselineStore,
    baseline_key: str,
    gate: BenchmarkGate | None = None,
) -> BenchmarkGateResult:
    """Evaluate a current report against an integrity-checked persisted baseline."""
    baseline = store.load(baseline_key)
    baseline.validate_for(suite, current)
    return (gate or BenchmarkGate()).evaluate(suite, baseline.report, current)


def evaluate_persisted_baseline_path(
    suite: BenchmarkSuite,
    current: EvaluationReport,
    *,
    store_path: str | Path,
    baseline_key: str,
    gate: BenchmarkGate | None = None,
) -> BenchmarkGateResult:
    """Convenience entry point for CI and command integrations using a store path."""
    return evaluate_persisted_baseline(
        suite,
        current,
        store=BenchmarkBaselineStore(store_path),
        baseline_key=baseline_key,
        gate=gate,
    )
