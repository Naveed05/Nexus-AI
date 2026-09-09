from nexus.core.models import ModelSpec, model_registry
from nexus.core.task import RiskLevel, Task


class TaskRouter:
    """Deterministic first-pass model routing for the NEXUS kernel."""

    def route(self, task: Task) -> ModelSpec:
        objective = task.objective.lower()

        if task.risk_level == RiskLevel.HIGH:
            return model_registry.get("astra")

        hard_signals = (
            "architecture",
            "debug",
            "debugging",
            "research",
            "complex",
            "reason",
            "agent",
            "multi-step",
        )
        if any(signal in objective for signal in hard_signals):
            return model_registry.get("astra")

        if task.capabilities:
            professional_capabilities = {
                "data_analysis",
                "machine_learning",
                "coding",
                "document_analysis",
                "research",
            }
            if professional_capabilities.intersection(task.capabilities):
                return model_registry.get("sol")

        if task.budget is not None and task.budget <= 1:
            return model_registry.get("luna")

        return model_registry.get("terra")


router = TaskRouter()
