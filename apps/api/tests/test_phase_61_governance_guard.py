from pathlib import Path

import pytest
from fastapi import HTTPException

from nexus.core.governance import GovernanceStore
from nexus.core.governance_guard import GovernanceGuard


def test_governance_store_bootstrap_and_token_auth(tmp_path: Path) -> None:
    store = GovernanceStore(tmp_path / "governance.sqlite3")
    assert store.principal_count() == 0
    principal = store.upsert_principal("admin", "tenant-a", "admin")
    token, secret = store.issue_token(principal.principal_id)
    authenticated = store.authenticate(secret)
    assert authenticated is not None
    assert authenticated.tenant_id == "tenant-a"
    assert store.authorize(authenticated, "govern", "tenant-a") is True
    assert store.authorize(authenticated, "execute", "tenant-b") is False


def test_governance_guard_requires_credentials_when_enforced(tmp_path: Path) -> None:
    store = GovernanceStore(tmp_path / "governance.sqlite3")
    guard = GovernanceGuard(store, enforced=True)
    class Request:
        headers = {}
    with pytest.raises(HTTPException) as error:
        guard.require(Request(), "execute")
    assert error.value.status_code == 401
