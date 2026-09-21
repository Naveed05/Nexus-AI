from nexus.core.observability import RuntimeObservability, RuntimeSnapshot


def test_existing_observability_tracks_runtime_lifecycle() -> None:
    telemetry = RuntimeObservability()
    telemetry.observe("running")
    telemetry.observe("completed")
    telemetry.observe("failed")

    snapshot = telemetry.snapshot()
    assert isinstance(snapshot, RuntimeSnapshot)
    assert snapshot.total_runs == 3
    assert snapshot.completed_runs == 1
    assert snapshot.failed_runs == 1
    assert snapshot.active_runs == 0


def test_observability_health_is_structured() -> None:
    telemetry = RuntimeObservability()
    body = telemetry.health()
    assert body["status"] == "healthy"
    assert body["active_runs"] == 0
