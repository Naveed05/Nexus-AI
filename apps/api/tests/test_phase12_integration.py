from nexus.core.advanced_intelligence import AdvancedIntelligencePipeline
from nexus.core.task import Task


def test_phase12_pipeline_is_deterministic_and_traceable() -> None:
    task = Task(
        objective="research and compare studies about reliable autonomous agents",
        context="Evaluate evidence before execution.",
        constraints=["use grounded evidence"],
    )
    memories = [
        "Reliable agents benefit from explicit verification.",
        "Reliable agents benefit from explicit verification.",
        "Long-horizon plans require checkpoints.",
    ]

    first = AdvancedIntelligencePipeline().assess(task, memories)
    second = AdvancedIntelligencePipeline().assess(task, memories)

    assert first == second
    assert first.plan.steps
    assert first.critique is not None
    assert first.improvement.original == first.assessment
    assert first.knowledge.evidence == tuple(dict.fromkeys(memories))
    assert first.memory_reasoning.supporting_items == first.knowledge.evidence
    assert 0.0 <= first.risk.score <= 1.0
    assert 0.0 <= first.failure.probability <= 1.0
    assert first.decision.action in {"proceed", "stage", "review"}
    assert first.safety.action in {"proceed", "stage", "review"}


def test_phase12_pipeline_never_executes_tools_and_low_confidence_is_guarded() -> None:
    task = Task(
        objective="research a complex repository implementation",
        context="",
    )
    result = AdvancedIntelligencePipeline().assess(task)

    assert result.plan.steps
    assert result.decision is not None
    assert result.safety is not None
    assert result.safety.allowed is False or result.safety.action == result.decision.action
    assert all(not item.status.value == "running" for item in result.plan.steps)


def test_phase12_pipeline_handles_empty_memory_safely() -> None:
    task = Task(objective="give a general explanation")
    result = AdvancedIntelligencePipeline().assess(task, [])

    assert result.knowledge.evidence == ()
    assert result.knowledge.confidence == 0.0
    assert result.memory_reasoning.confidence == 0.0
    assert "missing evidence" in result.memory_reasoning.gaps
