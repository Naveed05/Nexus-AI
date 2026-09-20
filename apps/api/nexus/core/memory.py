from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field, replace
from enum import Enum
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4


class MemoryKind(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    TASK_OUTCOME = "task_outcome"
    PROCEDURAL = "procedural"
    EPISODIC = "episodic"


@dataclass(frozen=True)
class MemoryRecord:
    """A durable, workspace-scoped fact that can safely re-enter future context."""

    content: str
    workspace_id: UUID | None = None
    memory_id: UUID = field(default_factory=uuid4)
    tags: tuple[str, ...] = ()
    importance: float = 0.5
    memory_kind: MemoryKind = MemoryKind.FACT
    source: str = "user"
    source_id: str | None = None
    expires_at: datetime | None = None
    supersedes_id: UUID | None = None
    archived: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    MAX_CONTENT_CHARS = 8_000
    MAX_TAGS = 16
    MAX_TAG_CHARS = 64

    def __post_init__(self) -> None:
        content = self.content.strip()
        if not content:
            raise ValueError("memory content cannot be empty")
        if len(content) > self.MAX_CONTENT_CHARS:
            raise ValueError(f"memory content cannot exceed {self.MAX_CONTENT_CHARS} characters")
        if any(ord(char) < 32 and char not in "\n\t" for char in content):
            raise ValueError("memory content cannot contain control characters")
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError("importance must be between 0 and 1")
        if not isinstance(self.memory_kind, MemoryKind):
            try:
                object.__setattr__(self, "memory_kind", MemoryKind(str(self.memory_kind)))
            except ValueError as exc:
                raise ValueError("unsupported memory kind") from exc
        if not self.source.strip():
            raise ValueError("memory source cannot be empty")
        if len(self.source) > 128:
            raise ValueError("memory source cannot exceed 128 characters")
        if self.source_id is not None and len(self.source_id) > 256:
            raise ValueError("memory source_id cannot exceed 256 characters")
        if self.expires_at is not None and (self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None):
            raise ValueError("expires_at must include a timezone offset")
        normalized_tags = tuple(sorted({tag.strip().lower() for tag in self.tags if tag.strip()}))
        if len(normalized_tags) > self.MAX_TAGS:
            raise ValueError(f"memory cannot contain more than {self.MAX_TAGS} tags")
        if any(len(tag) > self.MAX_TAG_CHARS for tag in normalized_tags):
            raise ValueError(f"memory tags cannot exceed {self.MAX_TAG_CHARS} characters")
        for timestamp_name, timestamp in (("created_at", self.created_at), ("updated_at", self.updated_at)):
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError(f"{timestamp_name} must include a timezone offset")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        object.__setattr__(self, "content", content)
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
        self._lock = RLock()
        if self._storage_path is not None:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self._storage_path, check_same_thread=False)
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY,
                    workspace_id TEXT,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    importance REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    memory_kind TEXT NOT NULL DEFAULT 'fact',
                    source TEXT NOT NULL DEFAULT 'user',
                    source_id TEXT,
                    expires_at TEXT,
                    supersedes_id TEXT,
                    archived INTEGER NOT NULL DEFAULT 0
                )"""
            )
            columns = {row[1] for row in self._connection.execute("PRAGMA table_info(memories)").fetchall()}
            migrations = {
                "memory_kind": "ALTER TABLE memories ADD COLUMN memory_kind TEXT NOT NULL DEFAULT 'fact'",
                "source": "ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT 'user'",
                "source_id": "ALTER TABLE memories ADD COLUMN source_id TEXT",
                "expires_at": "ALTER TABLE memories ADD COLUMN expires_at TEXT",
                "supersedes_id": "ALTER TABLE memories ADD COLUMN supersedes_id TEXT",
                "archived": "ALTER TABLE memories ADD COLUMN archived INTEGER NOT NULL DEFAULT 0",
            }
            for name, statement in migrations.items():
                if name not in columns:
                    self._connection.execute(statement)
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
            record.memory_kind.value,
            record.source,
            record.source_id,
            record.expires_at.isoformat() if record.expires_at else None,
            str(record.supersedes_id) if record.supersedes_id else None,
            int(record.archived),
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
            memory_kind=MemoryKind(row[7] or "fact"),
            source=row[8] or "user",
            source_id=row[9],
            expires_at=datetime.fromisoformat(row[10]) if row[10] else None,
            supersedes_id=UUID(row[11]) if row[11] else None,
            archived=bool(row[12]),
        )

    def _load(self) -> None:
        assert self._connection is not None
        with self._lock:
            rows = self._connection.execute(
                "SELECT memory_id, workspace_id, content, tags, importance, created_at, updated_at FROM memories"
            ).fetchall()
            self._records = {record.memory_id: record for record in map(self._deserialize, rows)}

    def _save(self, record: MemoryRecord) -> None:
        if self._connection is None:
            return
        with self._lock:
            self._connection.execute(
                """INSERT OR REPLACE INTO memories
                (memory_id, workspace_id, content, tags, importance, created_at, updated_at, memory_kind, source, source_id, expires_at, supersedes_id, archived)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                self._serialize(record),
            )
            self._connection.commit()

    def _delete_persisted(self, memory_id: UUID) -> None:
        if self._connection is None:
            return
        with self._lock:
            self._connection.execute("DELETE FROM memories WHERE memory_id = ?", (str(memory_id),))
            self._connection.commit()

    def remember(
        self,
        content: str,
        *,
        workspace_id: UUID | None = None,
        tags: tuple[str, ...] = (),
        importance: float = 0.5,
        memory_kind: MemoryKind = MemoryKind.FACT,
        source: str = "user",
        source_id: str | None = None,
        expires_at: datetime | None = None,
        supersedes_id: UUID | None = None,
        archived: bool = False,
    ) -> MemoryRecord:
        candidate = MemoryRecord(
            content=content, workspace_id=workspace_id, tags=tags, importance=importance,
            memory_kind=memory_kind, source=source, source_id=source_id,
            expires_at=expires_at, supersedes_id=supersedes_id, archived=archived,
        )
        with self._lock:
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
        return self.remember(content, workspace_id=workspace_id, tags=("task-outcome", "verified"), importance=0.7, memory_kind=MemoryKind.TASK_OUTCOME, source="task", source_id=clean_objective)

    @staticmethod
    def _validate_min_confidence(min_confidence: float) -> None:
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")

    def lifecycle_candidates(
        self,
        *,
        workspace_id: UUID | None = None,
        older_than_days: int = 30,
        min_importance: float = 0.0,
    ) -> tuple[MemoryRecord, ...]:
        """Return low-value/aging memories for explicit lifecycle review."""
        if older_than_days < 0:
            raise ValueError("older_than_days must be non-negative")
        if not 0.0 <= min_importance <= 1.0:
            raise ValueError("min_importance must be between 0 and 1")
        cutoff = datetime.now(timezone.utc).timestamp() - (older_than_days * 86400)
        with self._lock:
            return tuple(
                sorted(
                    (
                        record for record in self._records.values()
                        if record.workspace_id == workspace_id
                        and record.importance <= min_importance
                        and record.updated_at.timestamp() <= cutoff
                    ),
                    key=lambda record: (record.updated_at, str(record.memory_id)),
                )
            )

    def prune_lifecycle_candidates(
        self,
        *,
        workspace_id: UUID | None = None,
        older_than_days: int = 30,
        max_importance: float = 0.0,
    ) -> tuple[MemoryRecord, ...]:
        """Explicitly remove stale, low-importance memories; never cross workspaces."""
        candidates = self.lifecycle_candidates(
            workspace_id=workspace_id,
            older_than_days=older_than_days,
            min_importance=max_importance,
        )
        removed = []
        for record in candidates:
            removed.append(self.forget(record.memory_id, workspace_id=workspace_id))
        return tuple(removed)

    @staticmethod
    def _tokenize(text: str) -> tuple[str, ...]:
        return tuple(term.lower() for term in text.split() if term.strip())

    def recall_ranked(
        self,
        query: str,
        *,
        workspace_id: UUID | None = None,
        top_k: int = 5,
        min_confidence: float = 0.0,
        required_tags: tuple[str, ...] = (),
    ) -> tuple[MemoryMatch, ...]:
        if not query.strip():
            raise ValueError("query cannot be empty")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        self._validate_min_confidence(min_confidence)
        terms = set(self._tokenize(query))
        normalized_required_tags = {tag.strip().lower() for tag in required_tags if tag.strip()}
        with self._lock:
            candidates = [
                record for record in self._records.values()
                if record.workspace_id == workspace_id
                and not record.archived
                and (record.expires_at is None or record.expires_at > datetime.now(timezone.utc))
                and normalized_required_tags.issubset(record.tags)
            ]

            def signals(record: MemoryRecord) -> tuple[float, float]:
                haystack = f"{record.content} {' '.join(record.tags)}".lower()
                overlap = sum(1 for term in terms if term in haystack)
                relevance = overlap / len(terms) if terms else 0.0
                recency_days = max(0.0, (datetime.now(timezone.utc) - record.updated_at).total_seconds() / 86400)
                recency = 1.0 / (1.0 + recency_days / 30.0)
                confidence = relevance * record.importance * (0.75 + 0.25 * recency)
                # Round the public confidence signal to keep deterministic scores stable
                # across the tiny timestamp differences introduced during a recall.
                confidence = round(confidence, 10)
                return relevance, confidence

            scored = [(record, *signals(record)) for record in candidates]
            ranked = sorted(scored, key=lambda item: (item[2], item[1], item[0].importance, str(item[0].memory_id)), reverse=True)
            return tuple(
                MemoryMatch(record=record, relevance=relevance, confidence=confidence)
                for record, relevance, confidence in ranked[:top_k]
                if relevance > 0 and confidence >= min_confidence
            )

    def recall(
        self,
        query: str,
        *,
        workspace_id: UUID | None = None,
        top_k: int = 5,
        min_confidence: float = 0.0,
        required_tags: tuple[str, ...] = (),
    ) -> tuple[MemoryRecord, ...]:
        return tuple(
            match.record
            for match in self.recall_ranked(
                query,
                workspace_id=workspace_id,
                top_k=top_k,
                min_confidence=min_confidence,
                required_tags=required_tags,
            )
        )

    def recall_context(
        self,
        query: str,
        *,
        workspace_id: UUID | None = None,
        top_k: int = 5,
        max_chars: int = 6_000,
        min_confidence: float = 0.0,
    ) -> str:
        """Render bounded, confidence-aware memory guidance for agent reasoning."""
        if max_chars < 1:
            raise ValueError("max_chars must be at least 1")
        matches = self.recall_ranked(
            query,
            workspace_id=workspace_id,
            top_k=top_k,
            min_confidence=min_confidence,
        )
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

    def archive(self, memory_id: UUID, *, workspace_id: UUID | None = None) -> MemoryRecord:
        """Archive a memory without destroying its durable provenance."""
        with self._lock:
            record = self._records.get(memory_id)
            if record is None or record.workspace_id != workspace_id:
                raise KeyError(f"Unknown memory: {memory_id}")
            updated = replace(record, archived=True, updated_at=datetime.now(timezone.utc))
            self._records[memory_id] = updated
            self._save(updated)
            return updated

    def supersede(
        self,
        memory_id: UUID,
        content: str,
        *,
        workspace_id: UUID | None = None,
        importance: float | None = None,
        source: str = "user",
        source_id: str | None = None,
    ) -> MemoryRecord:
        """Create a replacement memory while retaining the predecessor relationship."""
        with self._lock:
            current = self._records.get(memory_id)
            if current is None or current.workspace_id != workspace_id:
                raise KeyError(f"Unknown memory: {memory_id}")
            replacement = self.remember(
                content,
                workspace_id=workspace_id,
                tags=current.tags,
                importance=current.importance if importance is None else importance,
                memory_kind=current.memory_kind,
                source=source,
                source_id=source_id,
                supersedes_id=memory_id,
            )
            self.archive(memory_id, workspace_id=workspace_id)
            return replacement

    def decay(
        self,
        *,
        workspace_id: UUID | None = None,
        older_than_days: int = 30,
        amount: float = 0.1,
        minimum_importance: float = 0.0,
    ) -> tuple[MemoryRecord, ...]:
        """Apply bounded importance decay to aging, active memories."""
        if older_than_days < 0:
            raise ValueError("older_than_days must be non-negative")
        if not 0.0 < amount <= 1.0:
            raise ValueError("amount must be greater than 0 and at most 1")
        if not 0.0 <= minimum_importance <= 1.0:
            raise ValueError("minimum_importance must be between 0 and 1")
        cutoff = datetime.now(timezone.utc).timestamp() - older_than_days * 86400
        updated_records: list[MemoryRecord] = []
        with self._lock:
            for record in tuple(self._records.values()):
                if (
                    record.workspace_id == workspace_id
                    and not record.archived
                    and record.updated_at.timestamp() <= cutoff
                    and record.importance > minimum_importance
                ):
                    updated = replace(
                        record,
                        importance=round(max(minimum_importance, record.importance - amount), 10),
                        updated_at=datetime.now(timezone.utc),
                    )
                    self._records[record.memory_id] = updated
                    self._save(updated)
                    updated_records.append(updated)
        return tuple(sorted(updated_records, key=lambda item: str(item.memory_id)))

    def reinforce(self, memory_id: UUID, *, workspace_id: UUID | None = None, amount: float = 0.1) -> MemoryRecord:
        """Increase a memory's importance without allowing it to exceed the safe bound."""
        if amount < 0:
            raise ValueError("amount must be non-negative")
        with self._lock:
            record = self._records.get(memory_id)
            if record is None or record.workspace_id != workspace_id:
                raise KeyError(f"Unknown memory: {memory_id}")
            updated = replace(record, importance=min(1.0, record.importance + amount), updated_at=datetime.now(timezone.utc))
            self._records[memory_id] = updated
            self._save(updated)
            return updated

    def stats(self, *, workspace_id: UUID | None = None) -> dict[str, int]:
        """Return bounded lifecycle counters for operational inspection."""
        now = datetime.now(timezone.utc)
        with self._lock:
            records = [record for record in self._records.values() if record.workspace_id == workspace_id]
        return {
            "total": len(records),
            "active": sum(1 for record in records if not record.archived and (record.expires_at is None or record.expires_at > now)),
            "archived": sum(1 for record in records if record.archived),
            "expired": sum(1 for record in records if not record.archived and record.expires_at is not None and record.expires_at <= now),
            "task_outcomes": sum(1 for record in records if record.memory_kind is MemoryKind.TASK_OUTCOME),
        }

    def list(self, *, workspace_id: UUID | None = None, include_archived: bool = False) -> tuple[MemoryRecord, ...]:
        with self._lock:
            return tuple(sorted(
                (record for record in self._records.values() if record.workspace_id == workspace_id and (include_archived or not record.archived)),
                key=lambda record: record.created_at,
            ))

    def forget(self, memory_id: UUID, *, workspace_id: UUID | None = None) -> MemoryRecord:
        with self._lock:
            record = self._records.get(memory_id)
            if record is None or record.workspace_id != workspace_id:
                raise KeyError(f"Unknown memory: {memory_id}")
            del self._records[memory_id]
            self._delete_persisted(memory_id)
            return record


_default_memory_path = os.getenv("NEXUS_MEMORY_DB", ".nexus/memory.db")
memory_store = MemoryStore(_default_memory_path)
