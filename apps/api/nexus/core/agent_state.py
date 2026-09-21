from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True)
class AgentCheckpoint:
    checkpoint_id: UUID
    step: int
    objective: str
    state: dict[str, Any]
    created_at: datetime


@dataclass
class AgentState:
    objective: str
    step: int = 0
    phase: str = "planning"
    context: dict[str, Any] = field(default_factory=dict)
    checkpoints: list[AgentCheckpoint] = field(default_factory=list)

    def checkpoint(self) -> AgentCheckpoint:
        snapshot = AgentCheckpoint(
            checkpoint_id=uuid4(),
            step=self.step,
            objective=self.objective,
            state={"phase": self.phase, "context": dict(self.context)},
            created_at=datetime.now(timezone.utc),
        )
        self.checkpoints.append(snapshot)
        return snapshot

    def restore(self, checkpoint: AgentCheckpoint) -> None:
        if checkpoint.objective != self.objective:
            raise ValueError("checkpoint objective does not match agent objective")
        self.step = checkpoint.step
        self.phase = str(checkpoint.state.get("phase", "planning"))
        self.context = dict(checkpoint.state.get("context", {}))

    def advance(self, phase: str, **context: Any) -> None:
        if not phase.strip():
            raise ValueError("phase cannot be empty")
        self.step += 1
        self.phase = phase.strip()
        self.context.update(context)
