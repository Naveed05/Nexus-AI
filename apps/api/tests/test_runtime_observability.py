from nexus.core.observability import RuntimeObservability


def test_runtime_observability_tracks_lifecycle():
    metrics = RuntimeObservability()
    metrics.observe("running")
    metrics.observe("completed")
    metrics.observe("running")
    metrics.observe("failed")

    snapshot = metrics.snapshot()
    assert snapshot.total_runs == 4
    assert snapshot.completed_runs == 1
    assert snapshot.failed_runs == 1
    assert snapshot.active_runs == 0
    assert metrics.health()["status"] == "healthy"
