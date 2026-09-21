from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

@dataclass(frozen=True)
class ContextEntry:
    key: str
    value: Any
    source_agent: str
    version: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass(frozen=True)
class AgentHandoff:
    handoff_id: UUID
    from_agent: str
    to_agent: str
    objective: str
    context: tuple[ContextEntry, ...]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class SharedAgentContext:
    """Bounded shared context with optimistic versioning and explicit provenance."""
    def __init__(self, max_entries: int = 256) -> None:
        if max_entries < 1: raise ValueError("max_entries must be at least 1")
        self.max_entries = max_entries
        self._entries: dict[str, ContextEntry] = {}

    def put(self, key: str, value: Any, source_agent: str, expected_version: int | None = None) -> ContextEntry:
        if not key.strip() or not source_agent.strip(): raise ValueError("key and source_agent cannot be empty")
        current = self._entries.get(key)
        version = current.version if current else 0
        if expected_version is not None and expected_version != version: raise ValueError(f"context version conflict for {key}")
        if current is None and len(self._entries) >= self.max_entries: raise ValueError("shared context capacity exceeded")
        entry = ContextEntry(key.strip(), value, source_agent.strip(), version + 1)
        self._entries[key.strip()] = entry
        return entry

    def get(self, key: str) -> ContextEntry | None: return self._entries.get(key)
    def snapshot(self) -> tuple[ContextEntry, ...]: return tuple(self._entries.values())

    def handoff(self, from_agent: str, to_agent: str, objective: str, keys: tuple[str, ...]) -> AgentHandoff:
        context = tuple(self._entries[key] for key in keys if key in self._entries)
        return AgentHandoff(uuid4(), from_agent, to_agent, objective, context)
