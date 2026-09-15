from nexus.core.orchestration_engine import OrchestrationEngine
from nexus.core.task import Task


def test_engine_completes_plan_with_verification_and_checkpoint(tmp_path) -> None:
    engine = OrchestrationEngine()
    path = tmp_path / "orchestration.json"
    result = engine.run(
        Task(objective="Write a summary"),
        executor=lambda decision: {"step": decision.step_id},
        verifier=lambda value: True,
        checkpoint_path=str(path),
    )

    assert result.status == "completed"
    assert result.steps_executed == 4
    assert result.retries == 0
    assert path.exists()
    assert [event.event for event in engine.audit.events()].count("completed") == 4


def test_engine_retries_verified_failure_within_budget() -> None:
    engine = OrchestrationEngine()
    verification_attempts = 0

    def verify(value) -> bool:
        nonlocal verification_attempts
        verification_attempts += 1
        return verification_attempts > 1

    result = engine.run(
        Task(objective="Write a summary"),
        executor=lambda decision: decision.step_id,
        verifier=verify,
    )

    assert result.status == "completed"
    assert result.retries == 1
    assert result.steps_executed == 5
    assert any(event.event == "retry" for event in engine.audit.events())


def test_engine_halts_after_recovery_budget_is_exhausted() -> None:
    engine = OrchestrationEngine()
    result = engine.run(
        Task(objective="Write a summary"),
        executor=lambda decision: decision.step_id,
        verifier=lambda value: False,
    )

    assert result.status == "failed"
    assert result.retries == 1
    assert result.steps_executed == 2
    assert any(event.event == "halt" for event in engine.audit.events())


def test_engine_rejects_invalid_cycle_budget() -> None:
    engine = OrchestrationEngine()
    try:
        engine.run(
            Task(objective="Write a summary"),
            executor=lambda decision: decision.step_id,
            verifier=lambda value: True,
            max_cycles=0,
        )
    except ValueError as exc:
        assert "max_cycles" in str(exc)
    else:
        raise AssertionError("invalid cycle budget should be rejected")
