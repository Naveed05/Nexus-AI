from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    objective: str = Field(min_length=1, max_length=20_000)


class TaskResponse(BaseModel):
    task_id: str
    objective: str
    status: str
