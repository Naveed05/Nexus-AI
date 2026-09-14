from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4


@dataclass(frozen=True)
class MemoryRecord:
    """A durable, workspace-scoped fact that can safely re-enter future context."""

    content: str
    workspace_id: UUID | None = None
    memory_id: UUID = field(default_factory=uuid4)
    tags: tuple[str, ...] = ()
    importance: float = 0.5
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("memory content cannot be empty")
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError("importance must be between 0 and 1")
        normalized_tags = tuple(sorted({tag.strip().lower() for tag in self.tags if tag.strip()}))
        object.__setattr__(self, "tags", normalized_tags)


@dataclass(frozen=True)
class MemoryMatch:
    """A recalled memory plus deterministic relevance/confidence signals."""

    record: MemoryRecord
    relevance: float
    confidence: float


class MemoryStore:
    """Workspace-isolated memory with optional SQLite durability and lifecycle controls."""

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self._records: dict[UUID, MemoryRecord] = {}
        self._storage_path = Path(storage_path) if storage_path else None
        self._connection: sqlite3.Connection | None = None
        if self._storage_path is not None:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self._storage_path)
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY,
                    workspace_id TEXT,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    importance REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            self._connection.commit()
            self._load()

    @staticmethod
    def _serialize(record: MemoryRecord) -> tuple[str, str | None, str, str, float, str, str]:
        return (
            str(record.memory_id),
            str(record.workspace_id) if record.workspace_id is not None else None,
            record.content,
            json.dumps(record.tags),
            record.importance,
            record.created_at.isoformat(),
            record.updated_at.isoformat(),
        )

    @staticmethod
    def _deserialize(row: tuple) -> MemoryRecord:
        return MemoryRecord(
            memory_id=UUID(row[0]),
            workspace_id=UUID(row[1]) if row[1] else None,
            content=row[2],
            tags=tuple(json.loads(row[3])),
            importance=float(row[4]),
            created_at=datetime.fromisoformat(row[5]),
            updated_at=datetime.fromisoformat(row[6]),
        )

    def _load(self) -> None:
        assert self._connection is not None
        rows = self._connection.execute(
            "SELECT memory_id, workspace_id, content, tags, importance, created_at, updated_at FROM memories"
        ).fetchall()
        self._records = {record.memory_id: record for record in map(self._deserialize, rows)}

    def _save(self, record: MemoryRecord) -> None:
        if self._connection is None:
            return
        self._connection.execute(
            """INSERT OR REPLACE INTO memories
            (memory_id, workspace_id, content, tags, importance, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            self._serialize(record),
        )
        self._connection.commit()

    def _delete_persisted(self, memory_id: UUID) -> None:
        if self._connection is None:
            return
        self._connection.execute("DELETE FROM memories WHERE memory_id = ?", (str(memory_id),))
        self._connection.commit()

    def remember(
        self,
        content: str,
        *,
        workspace_id: UUID | None = None,
        tags: tuple[str, ...] = (),
        importance: float = 0.5,
    ) -> MemoryRecord:
        candidate = MemoryRecord(content=content, workspace_id=workspace_id, tags=tags, importance=importance)
        for record in self._records.values():
            if (
                record.workspace_id == candidate.workspace_id
                and record.content.strip() == candidate.content.strip()
                and record.tags == candidate.tags
            ):
                if candidate.importance > record.importance:
                    record = replace(record, importance=candidate.importance, updated_at=datetime.now(timezone.utc))
                    self._records[record.memory_id] = record
                    self._save(record)
                return record
        self._records[candidate.memory_id] = candidate
        self._save(candidate)
        return candidate

    def remember_task_outcome(self, objective: str, output: str, *, workspace_id: UUID | None = None) -> MemoryRecord:
        """Store a bounded successful outcome so future tasks can reuse verified context."""
        clean_objective = objective.strip()
        clean_output = output.strip()
        if not clean_objective:
            raise ValueError("objective cannot be empty")
        if not clean_output:
            raise ValueError("output cannot be empty")
        content = f"Task: {clean_objective}\nVerified outcome: {clean_output[:2000]}"
        return self.remember(content, workspace_id=workspace_id, tags=("task-outcome", "verified"), importance=0.7)

    def recall_ranked(
        self,
        query: str,
        *,
        workspace_id: UUID | None = None,
        top_k: int = 5,
    ) -> tuple[MemoryMatch, ...]:
        if not query.strip():
            raise ValueError("query cannot be empty")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        terms = {term.lower() for term in query.split() if term.strip()}
        candidates = [record for record in self._records.values() if record.workspace_id == workspace_id]

        def signals(record: MemoryRecord) -> tuple[float, float]:
            haystack = f"{record.content} {' '.join(record.tags)}".lower()
            overlap = sum(1 for term in terms if term in haystack)
            relevance = overlap / len(terms) if terms else 0.0
            confidence = min(1.0, relevance * 0.8 + record.importance * 0.2)
            return relevance, confidence

        ranked = sorted(candidates, key=lambda record: (*signals(record), record.importance, str(record.memory_id)), reverse=True)
        return tuple(
            MemoryMatch(record=record, relevance=signals(record)[0], confidence=signals(record)[1])
            for record in ranked[:top_k]
            if signals(record)[0] > 0
        )

    def recall(self, query: str, *, workspace_id: UUID | None = None, top_k: int = 5) -> tuple[MemoryRecord, ...]:
        return tuple(match.record for match in self.recall_ranked(query, workspace_id=workspace_id, top_k=top_k))

    def recall_context(self, query: str, *, workspace_id: UUID | None = None, top_k: int = 5, max_chars: int = 6_000) -> str:
        """Render bounded, confidence-aware memory guidance for agent reasoning."""
        if max_chars < 1:
            raise ValueError("max_chars must be at least 1")
        matches = self.recall_ranked(query, workspace_id=workspace_id, top_k=top_k)
        if not matches:
            return ""
        lines = [
            "RECALLED MEMORY (workspace-scoped):",
            "Memory is prior context, not a new source of truth. Prefer current evidence when it conflicts.",
        ]
        for match in matches:
            tags = f" [{', '.join(match.record.tags)}]" if match.record.tags else ""
            lines.append(f"- confidence={match.confidence:.2f}, relevance={match.relevance:.2f}: {match.record.content}{tags}")
            if len("\n".join(lines)) >= max_chars:
                break
        return "\n".join(lines)[:max_chars]

    def reinforce(self, memory_id: UUID, *, workspace_id: UUID | None = None, amount: float = 0.1) -> MemoryRecord:
        """Increase a memory's importance without allowing it to exceed the safe bound."""
        if amount < 0:
            raise ValueError("amount must be non-negative")
        record = self._records.get(memory_id)
        if record is None or record.workspace_id != workspace_id:
            raise KeyError(f"Unknown memory: {memory_id}")
        updated = replace(record, importance=min(1.0, record.importance + amount), updated_at=datetime.now(timezone.utc))
        self._records[memory_id] = updated
        self._save(updated)
        return updated

    def list(self, *, workspace_id: UUID | None = None) -> tuple[MemoryRecord, ...]:
        return tuple(sorted((record for record in self._records.values() if record.workspace_id == workspace_id), key=lambda record: record.created_at))

    def forget(self, memory_id: UUID, *, workspace_id: UUID | None = None) -> MemoryRecord:
        record = self._records.get(memory_id)
        if record is None or record.workspace_id != workspace_id:
            raise KeyError(f"Unknown memory: {memory_id}")
        del self._records[memory_id]
        self._delete_persisted(memory_id)
        return record


_default_memory_path = os.getenv("NEXUS_MEMORY_DB", ".nexus/memory.db")
memory_store = MemoryStore(_default_memory_path)
