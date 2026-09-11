from nexus.core.state import PlanStep
from nexus.core.task import Task


class TaskPlanner:
    """Creates deterministic, task-aware execution graphs for the agent kernel."""

    _data_signals = (
        "dataset",
        "data analysis",
        "dataframe",
        "csv",
        "xlsx",
        "eda",
        "exploratory data",
        "machine learning",
        "model training",
    )
    _research_signals = (
        "research",
        "literature",
        "compare studies",
        "investigate",
        "find sources",
    )
    _coding_signals = (
        "code",
        "coding",
        "debug",
        "repository",
        "repo",
        "implement",
        "fix bug",
        "test",
    )

    def _contains(self, objective: str, signals: tuple[str, ...]) -> bool:
        return any(signal in objective for signal in signals)

    def plan(self, task: Task) -> list[PlanStep]:
        objective = task.objective.strip()
        text = objective.lower()

        if self._contains(text, self._data_signals):
            return [
                PlanStep("understand", f"Understand the objective: {objective}", execution_required=False),
                PlanStep("inspect_data", "Inspect the dataset structure, schema, missingness, and basic quality.", depends_on=("understand",)),
                PlanStep("analyze_data", objective, depends_on=("inspect_data",)),
                PlanStep("verify", "Verify the analysis against the task objective, constraints, and observed data.", depends_on=("analyze_data",), execution_required=False),
                PlanStep("deliver", "Prepare the verified analysis and useful artifacts for the user.", depends_on=("verify",), execution_required=False),
            ]

        if self._contains(text, self._coding_signals):
            return [
                PlanStep("understand", f"Understand the requested engineering task: {objective}", execution_required=False),
                PlanStep("inspect_code", "Inspect the relevant code, tests, and repository context.", depends_on=("understand",)),
                PlanStep("implement", objective, depends_on=("inspect_code",)),
                PlanStep("verify", "Run or reason through relevant tests and verify the implementation against the objective.", depends_on=("implement",), execution_required=False),
                PlanStep("deliver", "Summarize the completed engineering work and verification status.", depends_on=("verify",), execution_required=False),
            ]

        if self._contains(text, self._research_signals):
            return [
                PlanStep("understand", f"Understand the research objective: {objective}", execution_required=False),
                PlanStep("research", objective, depends_on=("understand",)),
                PlanStep("synthesize", "Synthesize the evidence into a grounded answer.", depends_on=("research",)),
                PlanStep("verify", "Check claims for consistency with the gathered evidence.", depends_on=("synthesize",), execution_required=False),
                PlanStep("deliver", "Prepare the verified research result with clear supporting evidence.", depends_on=("verify",), execution_required=False),
            ]

        return [
            PlanStep("understand", f"Understand the objective: {objective}", execution_required=False),
            PlanStep("execute", objective, depends_on=("understand",)),
            PlanStep("verify", "Verify the result against the task objective and constraints.", depends_on=("execute",), execution_required=False),
            PlanStep("deliver", "Prepare the final result for the user.", depends_on=("verify",), execution_required=False),
        ]


planner = TaskPlanner()
