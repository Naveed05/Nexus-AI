from nexus.core.state import PlanStep
from nexus.core.task import Task


class TaskPlanner:
    """Creates a deterministic execution plan before model/tool execution.

    This is intentionally conservative in the kernel. More advanced planning
    will later be delegated to the selected reasoning model.
    """

    def plan(self, task: Task) -> list[PlanStep]:
        objective = task.objective.strip()
        steps = [
            PlanStep(step_id="understand", objective=f"Understand the objective: {objective}"),
            PlanStep(step_id="execute", objective=objective),
            PlanStep(step_id="verify", objective="Verify the result against the task objective and constraints."),
            PlanStep(step_id="deliver", objective="Prepare the final result for the user."),
        ]
        return steps


planner = TaskPlanner()
