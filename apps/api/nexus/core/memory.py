from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("memory content cannot be empty")
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError("importance must be between 0 and 1")
        normalized_tags = tuple(sorted({tag.strip().lower() for tag in self.tags if tag.strip()}))
        object.__setattr__(self, "tags", normalized_tags)


class MemoryStore:
    """In-memory persistent-memory foundation with workspace isolation and deterministic recall."""

    def __init__(self) -> None:
        self._records: dict[UUID, MemoryRecord] = {}

    def remember(self, content: str, *, workspace_id: UUID | None = None, tags: tuple[str, ...] = (), importance: float = 0.5) -> MemoryRecord:
        record = MemoryRecord(content=content, workspace_id=workspace_id, tags=tags, importance=importance)
        self._records[record.memory_id] = record
        return record

    def recall(self, query: str, *, workspace_id: UUID | None = None, top_k: int = 5) -> tuple[MemoryRecord, ...]:
        if not query.strip():
            raise ValueError("query cannot be empty")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        terms = {term.lower() for term in query.split() if term.strip()}
        candidates = [record for record in self._records.values() if record.workspace_id == workspace_id]

        def score(record: MemoryRecord) -> tuple[float, float, str]:
            haystack = f"{record.content} {' '.join(record.tags)}".lower()
            overlap = sum(1 for term in terms if term in haystack)
            return (float(overlap), record.importance, str(record.memory_id))

        ranked = sorted(candidates, key=score, reverse=True)
        return tuple(record for record in ranked[:top_k] if score(record)[0] > 0)

    def recall_context(self, query: str, *, workspace_id: UUID | None = None, top_k: int = 5, max_chars: int = 6_000) -> str:
        """Render bounded recalled memories for safe insertion into an agent context."""
        if max_chars < 1:
            raise ValueError("max_chars must be at least 1")
        records = self.recall(query, workspace_id=workspace_id, top_k=top_k)
        if not records:
            return ""
        lines = ["RECALLED MEMORY (workspace-scoped):"]
        for record in records:
            tags = f" [{', '.join(record.tags)}]" if record.tags else ""
            lines.append(f"- {record.content}{tags}")
            if len("\n".join(lines)) >= max_chars:
                break
        return "\n".join(lines)[:max_chars]

    def list(self, *, workspace_id: UUID | None = None) -> tuple[MemoryRecord, ...]:
        return tuple(sorted((record for record in self._records.values() if record.workspace_id == workspace_id), key=lambda record: record.created_at))

    def forget(self, memory_id: UUID, *, workspace_id: UUID | None = None) -> MemoryRecord:
        record = self._records.get(memory_id)
        if record is None or record.workspace_id != workspace_id:
            raise KeyError(f"Unknown memory: {memory_id}")
        del self._records[memory_id]
        return record


memory_store = MemoryStore()
