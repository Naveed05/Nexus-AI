import pytest

from nexus.core.execution_state import ExecutionState, ExecutionStateMachine


def test_execution_state_machine_accepts_happy_path():
    machine = ExecutionStateMachine()
    machine.transition(ExecutionState.PLANNED, reason="plan ready")
    machine.transition(ExecutionState.APPROVED, reason="approved")
    machine.transition(ExecutionState.EXECUTING, reason="start execution")
    machine.transition(ExecutionState.VERIFYING, reason="verify output")
    machine.transition(ExecutionState.COMPLETED, reason="verified")

    assert machine.state is ExecutionState.COMPLETED
    assert len(machine.history) == 5


def test_execution_state_machine_rejects_illegal_transition():
    machine = ExecutionStateMachine()
    with pytest.raises(ValueError, match="invalid execution transition"):
        machine.transition(ExecutionState.COMPLETED, reason="skip lifecycle")


def test_execution_state_machine_is_terminal_after_failure():
    machine = ExecutionStateMachine()
    machine.transition(ExecutionState.PLANNED, reason="plan ready")
    machine.fail("execution error")

    assert machine.state is ExecutionState.FAILED
    with pytest.raises(ValueError, match="terminal"):
        machine.fail("second failure")


def test_execution_state_machine_rejects_blank_reason():
    machine = ExecutionStateMachine()
    with pytest.raises(ValueError, match="reason"):
        machine.transition(ExecutionState.PLANNED, reason=" ")
