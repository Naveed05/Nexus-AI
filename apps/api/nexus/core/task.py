from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Task(BaseModel):
    task_id: UUID = Field(default_factory=uuid4)
    objective: str = Field(min_length=1, max_length=20_000)
    context: str | None = None
    workspace_id: UUID | None = None
    constraints: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    budget: float | None = Field(default=None, ge=0)
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
