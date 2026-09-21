from fastapi.testclient import TestClient

from nexus.api import main


def test_rate_limit_returns_429(monkeypatch) -> None:
    main.rate_limiter._events.clear()
    main.rate_limiter.limit = 1
    client = TestClient(main.app)
    first = client.get("/api/v1/health", headers={"X-Nexus-User-ID": "rate-test"})
    second = client.get("/api/v1/health", headers={"X-Nexus-User-ID": "rate-test"})
    assert first.status_code == 200
    assert second.status_code == 429
    main.rate_limiter.limit = 120


def test_production_beta_key_is_required(monkeypatch) -> None:
    client = TestClient(main.app)
    monkeypatch.setattr(main.settings, "environment", "production")
    monkeypatch.setattr(main.settings, "beta_access_key", "beta-secret")
    assert client.get("/api/v1/health").status_code == 401
    assert client.get("/api/v1/health", headers={"X-Nexus-Beta-Key": "beta-secret"}).status_code == 200
    monkeypatch.setattr(main.settings, "environment", "development")
