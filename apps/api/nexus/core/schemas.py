from uuid import UUID

from pydantic import BaseModel, Field

from nexus.core.task import RiskLevel, TaskStatus


class TaskCreate(BaseModel):
    objective: str = Field(min_length=1, max_length=20_000)
    context: str | None = None
    workspace_id: UUID | None = None
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
    selected_model: str
    workspace_id: str | None = None


class ExecutionResponse(BaseModel):
    run_id: str
    task_id: str
    model: str
    response_id: str
    output: str
    verification_passed: bool
    verification_checks: dict[str, bool]
    verification_issues: list[str]
    grounding_score: float
    grounding: list[dict]
    tool_calls: int
    events: list[str]


class ResearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20_000)
    workspace_id: UUID
    max_queries: int = Field(default=4, ge=1, le=8)
    results_per_query: int = Field(default=5, ge=1, le=20)


class ResearchResponse(BaseModel):
    question: str
    workspace_id: str
    queries: list[str]
    evidence_count: int
    source_count: int
    document_count: int
    sources: list[dict]
    synthesis: dict
