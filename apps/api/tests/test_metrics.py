from nexus.core.metrics import ServiceMetrics


def test_service_metrics_render_prometheus() -> None:
    metrics = ServiceMetrics()
    metrics.observe_request(200)
    metrics.observe_request(503)

    body = metrics.prometheus("NEXUS AI")
    assert 'nexus_http_requests_total{service="NEXUS AI"} 2' in body
    assert 'nexus_http_errors_total{service="NEXUS AI"} 1' in body


def test_service_metrics_snapshot_is_stable() -> None:
    metrics = ServiceMetrics()
    assert metrics.snapshot() == {"requests": 0, "errors": 0}
