from nexus.core.runtime_metrics import ExecutionMetric, ExecutionMetrics


def test_execution_metrics_are_bounded_and_summarizable():
    metrics = ExecutionMetrics(max_samples=2)
    metrics.record(ExecutionMetric("1", "terra", 10, True))
    metrics.record(ExecutionMetric("2", "terra", 20, False))
    metrics.record(ExecutionMetric("3", "astra", 30, True))

    assert len(metrics.snapshot()) == 2
    assert metrics.summary()["count"] == 2
    assert metrics.summary()["verification_pass_rate"] == 0.5
    assert metrics.summary()["avg_duration_ms"] == 25.0
