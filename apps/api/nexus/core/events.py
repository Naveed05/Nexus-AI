from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID


class EventType(str, Enum):
    TASK_STARTED = "task_started"
    PLAN_CREATED = "plan_created"
    STEP_STARTED = "step_started"
    TOOL_CALLED = "tool_called"
    STEP_COMPLETED = "step_completed"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"


@dataclass(frozen=True)
class ExecutionEvent:
    event_type: EventType
    task_id: UUID
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
