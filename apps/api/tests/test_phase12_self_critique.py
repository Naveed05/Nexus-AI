from nexus.core.reasoning_engine import ReasoningAssessment, ReasoningEngine
from nexus.core.reasoning_improvement import ReasoningImprovementLoop
from nexus.core.self_critique import SelfCritiqueEngine
from nexus.core.task import Task


def test_self_critique_is_deterministic_and_structured():
    task = Task(objective="research and compare autonomous agent studies")
    assessment = ReasoningEngine().assess(task)

    first = SelfCritiqueEngine().critique(task, assessment)
    second = SelfCritiqueEngine().critique(task, assessment)

    assert first == second
    assert first.missing_evidence
    assert first.severity in {"low", "medium", "high"}


def test_improvement_loop_is_bounded_and_preserves_original_assessment():
    assessment = ReasoningAssessment(
        intent="research",
        complexity=0.8,
        confidence=0.9,
        risks=(),
        assumptions=("no additional task context was supplied",),
    )
    task = Task(objective="research autonomous agents")
    critique = SelfCritiqueEngine().critique(task, assessment)

    result = ReasoningImprovementLoop().improve(assessment, critique)

    assert result.original == assessment
    assert result.improved is not assessment
    assert result.improved.confidence <= assessment.confidence
    assert result.improved.complexity <= 1.0
    assert result.changes


def test_clean_reasoning_is_not_changed():
    assessment = ReasoningAssessment(
        intent="general",
        complexity=0.3,
        confidence=0.85,
        risks=(),
        assumptions=(),
    )
    task = Task(objective="summarize the supplied objective")
    critique = SelfCritiqueEngine().critique(task, assessment)
    result = ReasoningImprovementLoop().improve(assessment, critique)

    assert critique.severity == "low"
    assert result.improved == assessment
    assert result.changes == ()
