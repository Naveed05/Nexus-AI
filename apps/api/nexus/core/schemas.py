from pydantic import BaseModel, Field

from nexus.core.task import RiskLevel, TaskStatus


class TaskCreate(BaseModel):
    objective: str = Field(min_length=1, max_length=20_000)
    context: str | None = None
    constraints: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    budget: float | None = Field(default=None, ge=0)


class TaskResponse(BaseModel):
    task_id: str
    objective: str
    status: TaskStatus
    risk_level: RiskLevel
    created_at: str
    capabilities: list[str]
