from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from threading import RLock
from typing import Protocol


class CacheBackend(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, *, ttl_seconds: int) -> None: ...
    def delete(self, key: str) -> None: ...


@dataclass
class _CacheEntry:
    value: str
    expires_at: datetime


class TTLCache:
    """Bounded in-process cache implementing the shared-cache contract."""

    def __init__(self, *, max_entries: int = 1024) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self.max_entries = max_entries
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = RLock()

    def get(self, key: str) -> str | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= datetime.now(timezone.utc):
                self._entries.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be at least 1")
        with self._lock:
            if key not in self._entries and len(self._entries) >= self.max_entries:
                oldest = min(self._entries, key=lambda item: self._entries[item].expires_at)
                self._entries.pop(oldest, None)
            self._entries[key] = _CacheEntry(
                value, datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            )

    def delete(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def health(self) -> dict[str, str]:
        return {"status": "ready", "backend": "memory", "consistency": "best-effort"}


@dataclass(frozen=True)
class StoredObject:
    object_id: str
    size_bytes: int
    sha256: str


class ObjectStore(Protocol):
    def put(self, payload: bytes, *, namespace: str) -> StoredObject: ...
    def get(self, object_id: str, *, namespace: str) -> bytes: ...


class ContentAddressedObjectStore:
    """Local object-store boundary with deterministic content-addressed IDs."""

    def __init__(self, root: str) -> None:
        from pathlib import Path
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def put(self, payload: bytes, *, namespace: str) -> StoredObject:
        namespace = namespace.strip()
        if not namespace:
            raise ValueError("namespace cannot be empty")
        digest = hashlib.sha256(payload).hexdigest()
        object_id = f"{namespace}/{digest}"
        target = self.root / namespace / digest
        with self._lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(payload)
        return StoredObject(object_id, len(payload), digest)

    def get(self, object_id: str, *, namespace: str) -> bytes:
        from pathlib import Path
        prefix = f"{namespace}/"
        if not object_id.startswith(prefix):
            raise ValueError("object does not belong to namespace")
        digest = object_id[len(prefix):]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise KeyError("invalid object id")
        target = self.root / Path(namespace) / digest
        if not target.is_file():
            raise KeyError(f"unknown object: {object_id}")
        return target.read_bytes()

    def health(self) -> dict[str, str]:
        return {"status": "ready", "backend": "filesystem", "consistency": "content-addressed"}
