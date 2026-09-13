from types import SimpleNamespace
from uuid import uuid4

from nexus.core.task import Task
from nexus.core.verification import OutputVerifier


def test_verifier_accepts_valid_observable_output() -> None:
    task = Task(task_id=uuid4(), objective="Explain this result")
    result = OutputVerifier().verify(task, "The result is valid.")

    assert result.passed is True
    assert result.checks["non_empty_output"] is True
    assert result.checks["objective_present"] is True
    assert result.checks["tool_calls_recorded"] is True
    assert result.checks["grounded_research"] is True
    assert result.grounding_score == 1.0


def test_verifier_rejects_empty_output() -> None:
    task = Task(task_id=uuid4(), objective="Explain this result")
    result = OutputVerifier().verify(task, "   ")

    assert result.passed is False
    assert result.checks["non_empty_output"] is False
    assert "Model returned empty output." in result.issues


def test_verifier_rejects_missing_objective() -> None:
    task = Task(task_id=uuid4(), objective="Explain this result")
    task.objective = "   "

    result = OutputVerifier().verify(task, "Some output")

    assert result.passed is False
    assert result.checks["objective_present"] is False
    assert "Task objective is empty." in result.issues


def test_verifier_accepts_research_output_with_retrieved_citation() -> None:
    task = Task(task_id=uuid4(), objective="Research hybrid retrieval")
    tool_call = SimpleNamespace(tool_name="search_knowledge")
    evidence = (
        {
            "citation": "architecture.md — chunk 1",
            "document_id": str(uuid4()),
            "chunk_id": str(uuid4()),
            "text": "NEXUS uses hybrid retrieval.",
        },
    )

    result = OutputVerifier().verify(
        task,
        "NEXUS uses hybrid retrieval. [Source: architecture.md — chunk 1]",
        (tool_call,),
        grounded_evidence=evidence,
    )

    assert result.passed is True
    assert result.checks["grounded_research"] is True
    assert result.grounding[0].supported is True
    assert result.grounding_score == 1.0


def test_verifier_rejects_citation_not_supported_by_evidence() -> None:
    task = Task(task_id=uuid4(), objective="Research hybrid retrieval")
    tool_call = SimpleNamespace(tool_name="search_knowledge")
    evidence = (
        {
            "citation": "architecture.md — chunk 1",
            "text": "NEXUS uses hybrid retrieval.",
        },
    )

    result = OutputVerifier().verify(
        task,
        "Mars is made entirely of cheese. [Source: architecture.md — chunk 1]",
        (tool_call,),
        grounded_evidence=evidence,
    )

    assert result.passed is False
    assert result.checks["grounded_research"] is False
    assert result.grounding[0].supported is False
    assert result.grounding_score == 0.0
    assert "not supported" in result.issues[0]


def test_verifier_rejects_research_output_without_citation() -> None:
    task = Task(task_id=uuid4(), objective="Research hybrid retrieval")
    tool_call = SimpleNamespace(tool_name="search_knowledge")
    evidence = (
        {
            "citation": "architecture.md — chunk 1",
            "text": "NEXUS uses hybrid retrieval.",
        },
    )

    result = OutputVerifier().verify(
        task,
        "NEXUS uses hybrid retrieval.",
        (tool_call,),
        grounded_evidence=evidence,
    )

    assert result.passed is False
    assert result.checks["grounded_research"] is False
    assert "does not contain a citation" in result.issues[0]
    assert result.grounding_score == 0.0


def test_verifier_rejects_citation_not_in_retrieved_evidence() -> None:
    task = Task(task_id=uuid4(), objective="Research hybrid retrieval")
    tool_call = SimpleNamespace(tool_name="search_knowledge")
    evidence = (
        {
            "citation": "architecture.md — chunk 1",
            "text": "NEXUS uses hybrid retrieval.",
        },
    )

    result = OutputVerifier().verify(
        task,
        "NEXUS uses hybrid retrieval. [Source: unknown.md — chunk 9]",
        (tool_call,),
        grounded_evidence=evidence,
    )

    assert result.passed is False
    assert result.checks["grounded_research"] is False
    assert result.grounding_score == 0.0
    assert "unsupported citations" in result.issues[0]


def test_verifier_rejects_research_without_retrieved_evidence() -> None:
    task = Task(task_id=uuid4(), objective="Research hybrid retrieval")
    tool_call = SimpleNamespace(tool_name="search_knowledge")

    result = OutputVerifier().verify(
        task,
        "NEXUS uses hybrid retrieval. [Source: architecture.md — chunk 1]",
        (tool_call,),
    )

    assert result.passed is False
    assert result.checks["grounded_research"] is False
    assert result.grounding_score == 0.0
    assert "no retrieved evidence" in result.issues[0]


def test_non_research_task_does_not_require_grounding() -> None:
    task = Task(task_id=uuid4(), objective="Calculate 2 + 2")
    result = OutputVerifier().verify(task, "4")
    assert result.passed is True
    assert result.grounding == ()
    assert result.grounding_score == 1.0
