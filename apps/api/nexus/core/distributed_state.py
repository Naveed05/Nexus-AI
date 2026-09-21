from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from threading import RLock
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class StateRecord:
    key: str
    value: dict[str, Any]
    version: int
    updated_at: datetime


class StateConflictError(RuntimeError):
    """Raised when a compare-and-swap update observes a newer version."""


class DistributedStateStore:
    """Versioned durable state boundary ready for a shared transactional backend."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = RLock()
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS distributed_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _encode(value: dict[str, Any]) -> str:
        import json
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _decode(value: str) -> dict[str, Any]:
        import json
        return json.loads(value)

    def get(self, key: str) -> StateRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM distributed_state WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return StateRecord(
            row["key"], self._decode(row["value"]), row["version"],
            datetime.fromisoformat(row["updated_at"]),
        )

    def put(self, key: str, value: dict[str, Any], *, expected_version: int | None = None) -> StateRecord:
        now = datetime.now(timezone.utc)
        encoded = self._encode(value)
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT version FROM distributed_state WHERE key = ?", (key,)).fetchone()
            current = None if row is None else int(row["version"])
            if expected_version is not None and current != expected_version:
                raise StateConflictError(f"state version conflict for {key}")
            version = 1 if current is None else current + 1
            if current is None:
                conn.execute(
                    "INSERT INTO distributed_state VALUES (?, ?, ?, ?)",
                    (key, encoded, version, now.isoformat()),
                )
            else:
                conn.execute(
                    "UPDATE distributed_state SET value = ?, version = ?, updated_at = ? WHERE key = ?",
                    (encoded, version, now.isoformat(), key),
                )
            conn.commit()
        return StateRecord(key, value, version, now)

    def delete(self, key: str, *, expected_version: int | None = None) -> bool:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT version FROM distributed_state WHERE key = ?", (key,)).fetchone()
            if row is None:
                return False
            if expected_version is not None and int(row["version"]) != expected_version:
                raise StateConflictError(f"state version conflict for {key}")
            conn.execute("DELETE FROM distributed_state WHERE key = ?", (key,))
            conn.commit()
            return True

    def health(self) -> dict[str, str]:
        with self._connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ready", "backend": "sqlite", "consistency": "versioned-cas"}


def state_key(namespace: str, identifier: UUID | str) -> str:
    namespace = namespace.strip()
    if not namespace:
        raise ValueError("namespace cannot be empty")
    return f"{namespace}:{identifier}"
