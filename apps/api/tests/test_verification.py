from uuid import uuid4

from nexus.core.task import Task
from nexus.core.verification import OutputVerifier


def test_verifier_accepts_valid_observable_output() -> None:
    task = Task(task_id=uuid4(), objective="Explain this result")
    result = OutputVerifier().verify(task, "The result is valid.")

    assert result.passed is True
    assert result.checks["non_empty_output"] is True
    assert result.checks["objective_present"] is True


def test_verifier_rejects_empty_output() -> None:
    task = Task(task_id=uuid4(), objective="Explain this result")
    result = OutputVerifier().verify(task, "   ")

    assert result.passed is False
    assert "Model returned empty output." in result.issues
