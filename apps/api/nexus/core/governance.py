"""Enterprise security and governance primitives for NEXUS."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROLES = frozenset({"viewer", "operator", "admin"})
ROLE_PERMISSIONS = {
    "viewer": frozenset({"read"}),
    "operator": frozenset({"read", "execute"}),
    "admin": frozenset({"read", "execute", "govern"}),
}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def hash_secret(secret: str, salt: str) -> str:
    return hashlib.sha256(("{0}:{1}".format(salt, secret)).encode()).hexdigest()

@dataclass(frozen=True)
class Principal:
    principal_id: str
    tenant_id: str
    role: str
    created_at: str
    active: bool = True

@dataclass(frozen=True)
class AccessToken:
    token_id: str
    principal_id: str
    token_hash: str
    created_at: str
    expires_at: str | None
    active: bool = True

class GovernanceError(ValueError):
    pass

class GovernanceStore:
    """Durable tenant-scoped RBAC, token metadata, and governance audit."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS principals (
                    principal_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    role TEXT NOT NULL, created_at TEXT NOT NULL, active INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS access_tokens (
                    token_id TEXT PRIMARY KEY, principal_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
                    expires_at TEXT, active INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS governance_audit (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL,
                    principal_id TEXT, action TEXT NOT NULL, resource TEXT NOT NULL,
                    decision TEXT NOT NULL, metadata_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_governance_audit_tenant
                    ON governance_audit(tenant_id, created_at);
            """)

    def upsert_principal(self, principal_id: str, tenant_id: str, role: str = "viewer") -> Principal:
        principal_id, tenant_id, role = principal_id.strip(), tenant_id.strip(), role.strip().lower()
        if not principal_id or not tenant_id:
            raise GovernanceError("principal_id and tenant_id are required")
        if role not in ROLES:
            raise GovernanceError("unknown role: " + role)
        created = _now()
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT created_at FROM principals WHERE principal_id=?", (principal_id,)).fetchone()
            created = row[0] if row else created
            db.execute(
                """INSERT INTO principals(principal_id,tenant_id,role,created_at,active)
                   VALUES(?,?,?,?,1)
                   ON CONFLICT(principal_id) DO UPDATE SET tenant_id=excluded.tenant_id, role=excluded.role, active=1""",
                (principal_id, tenant_id, role, created),
            )
        return Principal(principal_id, tenant_id, role, created, True)

    def get_principal(self, principal_id: str) -> Principal | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT principal_id,tenant_id,role,created_at,active FROM principals WHERE principal_id=?", (principal_id,)).fetchone()
        return Principal(row[0], row[1], row[2], row[3], bool(row[4])) if row else None

    def issue_token(self, principal_id: str, expires_at: str | None = None) -> tuple[AccessToken, str]:
        principal = self.get_principal(principal_id)
        if principal is None or not principal.active:
            raise GovernanceError("principal is inactive or unknown")
        raw = secrets.token_urlsafe(32)
        token_id = secrets.token_urlsafe(12)
        salt = secrets.token_urlsafe(12)
        token_hash = hash_secret(raw, salt)
        stored_hash = salt + "$" + token_hash
        created = _now()
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO access_tokens(token_id,principal_id,token_hash,created_at,expires_at,active) VALUES(?,?,?,?,?,1)",
                       (token_id, principal_id, stored_hash, created, expires_at))
        return AccessToken(token_id, principal_id, stored_hash, created, expires_at, True), "nxs_" + token_id + "_" + raw

    def authenticate(self, presented: str) -> Principal | None:
        if not presented.startswith("nxs_"):
            return None
        try:
            _, token_id, raw = presented.split("_", 2)
        except ValueError:
            return None
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                """SELECT t.token_hash,p.principal_id,p.tenant_id,p.role,p.created_at,p.active,t.expires_at
                   FROM access_tokens t JOIN principals p ON p.principal_id=t.principal_id
                   WHERE t.token_id=? AND t.active=1""", (token_id,)).fetchone()
        if not row or not row[5] or "$" not in row[0]:
            return None
        salt, expected = row[0].split("$", 1)
        if not hmac.compare_digest(hash_secret(raw, salt), expected):
            return None
        if row[6] and datetime.fromisoformat(row[6]) <= datetime.now(timezone.utc):
            return None
        return Principal(row[1], row[2], row[3], row[4], True)

    def revoke_token(self, token_id: str) -> bool:
        with sqlite3.connect(self.path) as db:
            cur = db.execute("UPDATE access_tokens SET active=0 WHERE token_id=? AND active=1", (token_id,))
        return cur.rowcount > 0

    def authorize(self, principal: Principal, permission: str, tenant_id: str) -> bool:
        allowed = principal.active and principal.tenant_id == tenant_id and permission in ROLE_PERMISSIONS.get(principal.role, ())
        self.audit(tenant_id, principal.principal_id, "authorize:" + permission, "tenant", "allow" if allowed else "deny", {})
        return allowed

    def audit(self, tenant_id: str, principal_id: str | None, action: str, resource: str, decision: str, metadata: dict[str, Any]) -> None:
        safe = redact_secrets(metadata)
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO governance_audit(tenant_id,principal_id,action,resource,decision,metadata_json,created_at) VALUES(?,?,?,?,?,?,?)",
                       (tenant_id, principal_id, action, resource, decision, json.dumps(safe, sort_keys=True), _now()))

    def audit_events(self, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with sqlite3.connect(self.path) as db:
            rows = db.execute("""SELECT event_id,tenant_id,principal_id,action,resource,decision,metadata_json,created_at
                                 FROM governance_audit WHERE tenant_id=? ORDER BY event_id DESC LIMIT ?""",
                              (tenant_id, limit)).fetchall()
        return [{"event_id": r[0], "tenant_id": r[1], "principal_id": r[2], "action": r[3],
                 "resource": r[4], "decision": r[5], "metadata": json.loads(r[6]), "created_at": r[7]} for r in rows]

def redact_secrets(value: Any) -> Any:
    secret_names = {"password", "secret", "token", "api_key", "authorization", "private_key", "credential"}
    if isinstance(value, dict):
        return {str(k): "[REDACTED]" if str(k).lower() in secret_names else redact_secrets(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_secrets(v) for v in value]
    if isinstance(value, tuple):
        return [redact_secrets(v) for v in value]
    return value

def governance_payload(principal: Principal) -> dict[str, Any]:
    return {"principal_id": principal.principal_id, "tenant_id": principal.tenant_id,
            "role": principal.role, "permissions": sorted(ROLE_PERMISSIONS[principal.role]),
            "active": principal.active, "created_at": principal.created_at}
