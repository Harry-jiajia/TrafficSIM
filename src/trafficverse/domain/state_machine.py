"""Experiment lifecycle transition rules."""

from trafficverse.domain.enums import ErrorCode, ExperimentStatus
from trafficverse.domain.errors import InvalidStateTransitionError

_TRANSITIONS: dict[ExperimentStatus, frozenset[ExperimentStatus]] = {
    ExperimentStatus.CREATED: frozenset({ExperimentStatus.PREPARING}),
    ExperimentStatus.PREPARING: frozenset({ExperimentStatus.READY, ExperimentStatus.FAILED}),
    ExperimentStatus.READY: frozenset({ExperimentStatus.RUNNING, ExperimentStatus.FAILED}),
    ExperimentStatus.RUNNING: frozenset(
        {ExperimentStatus.PAUSED, ExperimentStatus.STOPPING, ExperimentStatus.FAILED}
    ),
    ExperimentStatus.PAUSED: frozenset(
        {ExperimentStatus.RUNNING, ExperimentStatus.STOPPING, ExperimentStatus.FAILED}
    ),
    ExperimentStatus.STOPPING: frozenset({ExperimentStatus.COMPLETED, ExperimentStatus.FAILED}),
    ExperimentStatus.COMPLETED: frozenset(),
    ExperimentStatus.FAILED: frozenset({ExperimentStatus.STOPPING}),
}


def can_transition(current: ExperimentStatus, target: ExperimentStatus) -> bool:
    """Return whether the transition is legal; self-transitions are idempotent."""

    return current == target or target in _TRANSITIONS[current]


def require_transition(current: ExperimentStatus, target: ExperimentStatus) -> None:
    """Raise a stable domain error when a transition is illegal."""

    if can_transition(current, target):
        return
    raise InvalidStateTransitionError(
        ErrorCode.INVALID_STATE_TRANSITION,
        f"cannot transition experiment from {current.value} to {target.value}",
        details={"current": current.value, "target": target.value},
    )
