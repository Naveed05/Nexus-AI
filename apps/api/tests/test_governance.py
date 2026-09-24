from datetime import datetime, timedelta, timezone

import pytest

from nexus.core.governance import GovernanceError, GovernanceStore, redact_secrets


def test_rbac_is_tenant_scoped_and_audited(tmp_path):
    store = GovernanceStore(tmp_path / "governance.sqlite3")
    admin = store.upsert_principal("alice", "tenant-a", "admin")
    viewer = store.upsert_principal("bob", "tenant-b", "viewer")

    assert store.authorize(admin, "govern", "tenant-a")
    assert not store.authorize(admin, "govern", "tenant-b")
    assert store.authorize(viewer, "read", "tenant-b")
    assert not store.authorize(viewer, "execute", "tenant-b")

    events = store.audit_events("tenant-a")
    assert any(event["decision"] == "deny" for event in events)


def test_token_is_one_time_secret_and_revocable(tmp_path):
    store = GovernanceStore(tmp_path / "governance.sqlite3")
    principal = store.upsert_principal("alice", "tenant-a", "operator")
    token, secret = store.issue_token(principal.principal_id)
    assert secret.startswith("nxs_")
    authenticated = store.authenticate(secret)
    assert authenticated is not None
    assert authenticated.tenant_id == "tenant-a"
    assert authenticated.role == "operator"
    assert store.revoke_token(token.token_id)
    assert store.authenticate(secret) is None


def test_expired_token_is_rejected(tmp_path):
    store = GovernanceStore(tmp_path / "governance.sqlite3")
    principal = store.upsert_principal("alice", "tenant-a", "operator")
    expires = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    _, secret = store.issue_token(principal.principal_id, expires)
    assert store.authenticate(secret) is None


def test_invalid_roles_and_missing_identity_are_rejected(tmp_path):
    store = GovernanceStore(tmp_path / "governance.sqlite3")
    with pytest.raises(GovernanceError):
        store.upsert_principal("", "tenant-a")
    with pytest.raises(GovernanceError):
        store.upsert_principal("alice", "tenant-a", "root")


def test_audit_redacts_credentials_recursively():
    payload = redact_secrets({"token": "secret", "nested": {"api_key": "value", "ok": "visible"}, "items": [{"password": "x"}]})
    assert payload["token"] == "[REDACTED]"
    assert payload["nested"]["api_key"] == "[REDACTED]"
    assert payload["nested"]["ok"] == "visible"
    assert payload["items"][0]["password"] == "[REDACTED]"


def test_governance_api_contract():
    from nexus.api.main import client

    created = client.post("/api/v1/governance/principals", json={"principal_id": "api-user", "tenant_id": "tenant-api", "role": "operator"})
    assert created.status_code == 201
    assert created.json()["permissions"] == ["execute", "read"]

    token = client.post("/api/v1/governance/tokens", json={"principal_id": "api-user"})
    assert token.status_code == 201
    secret = token.json()["token"]

    auth = client.post("/api/v1/governance/authorize", json={"principal_id": "api-user", "tenant_id": "tenant-api", "permission": "execute"})
    assert auth.status_code == 200
    assert auth.json()["allowed"] is True

    assert client.post("/api/v1/governance/tokens/" + token.json()["token_id"] + "/revoke").json()["revoked"] is True
    assert client.get("/api/v1/governance/audit?tenant_id=tenant-api").status_code == 200
