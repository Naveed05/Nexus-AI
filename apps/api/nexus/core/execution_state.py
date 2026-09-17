from dataclasses import dataclass
from enum import Enum
from typing import ClassVar


class ExecutionState(str, Enum):
    CREATED = "created"
    PLANNED = "planned"
    APPROVED = "approved"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ExecutionTransition:
    """Immutable record of one legal runtime state transition."""

    from_state: ExecutionState
    to_state: ExecutionState
    reason: str


class ExecutionStateMachine:
    """Fail-closed lifecycle guard for agent executions."""

    _ALLOWED: ClassVar[dict[ExecutionState, frozenset[ExecutionState]]] = {
        ExecutionState.CREATED: frozenset({ExecutionState.PLANNED, ExecutionState.FAILED}),
        ExecutionState.PLANNED: frozenset({ExecutionState.APPROVED, ExecutionState.EXECUTING, ExecutionState.FAILED}),
        ExecutionState.APPROVED: frozenset({ExecutionState.EXECUTING, ExecutionState.FAILED}),
        ExecutionState.EXECUTING: frozenset({ExecutionState.VERIFYING, ExecutionState.FAILED}),
        ExecutionState.VERIFYING: frozenset({ExecutionState.COMPLETED, ExecutionState.FAILED}),
        ExecutionState.COMPLETED: frozenset(),
        ExecutionState.FAILED: frozenset(),
    }

    def __init__(self, initial: ExecutionState = ExecutionState.CREATED) -> None:
        self._state = initial
        self._history: list[ExecutionTransition] = []

    @property
    def state(self) -> ExecutionState:
        return self._state

    @property
    def history(self) -> tuple[ExecutionTransition, ...]:
        return tuple(self._history)

    def can_transition(self, target: ExecutionState) -> bool:
        return target in self._ALLOWED[self._state]

    def transition(self, target: ExecutionState, *, reason: str) -> ExecutionTransition:
        if not reason.strip():
            raise ValueError("transition reason cannot be empty")
        if not self.can_transition(target):
            raise ValueError(f"invalid execution transition: {self._state.value} -> {target.value}")
        event = ExecutionTransition(self._state, target, reason.strip())
        self._history.append(event)
        self._state = target
        return event

    def fail(self, reason: str) -> ExecutionTransition:
        if self._state in {ExecutionState.COMPLETED, ExecutionState.FAILED}:
            raise ValueError(f"cannot fail terminal execution state: {self._state.value}")
        return self.transition(ExecutionState.FAILED, reason=reason)
