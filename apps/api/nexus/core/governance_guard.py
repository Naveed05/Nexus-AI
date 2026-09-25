from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request

from .governance import GovernanceStore, Principal


@dataclass(frozen=True)
class GovernanceDecision:
    principal: Principal
    permission: str
    tenant_id: str
    allowed: bool


class GovernanceGuard:
    """Single authorization boundary used by protected control-plane routes."""

    def __init__(self, store: GovernanceStore, enforced: bool = False) -> None:
        self.store = store
        self.enforced = enforced

    def principal(self, request: Request) -> Principal | None:
        presented = request.headers.get("Authorization", "")
        if presented.lower().startswith("bearer "):
            presented = presented[7:].strip()
        if not presented:
            presented = request.headers.get("X-Nexus-Access-Token", "").strip()
        if not presented:
            return None
        return self.store.authenticate(presented)

    def require(self, request: Request, permission: str, *, tenant_id: str | None = None) -> GovernanceDecision:
        if permission not in {"read", "execute", "govern"}:
            raise ValueError("unsupported governance permission")
        tenant = (tenant_id or request.headers.get("X-Nexus-Tenant-ID") or "local").strip()
        principal = self.principal(request)
        if principal is None:
            if not self.enforced:
                principal = Principal("local-user", tenant, "admin", "", True)
            else:
                raise HTTPException(status_code=401, detail="governance credentials required")
        allowed = self.store.authorize(principal, permission, tenant)
        if not allowed:
            raise HTTPException(status_code=403, detail="governance permission denied")
        return GovernanceDecision(principal, permission, tenant, True)

    def audit_mutation(self, decision: GovernanceDecision, action: str, resource: str, metadata: dict[str, Any] | None = None) -> None:
        self.store.audit(decision.tenant_id, decision.principal.principal_id, action, resource, "allow", metadata or {})
