import pytest

from trafficverse.domain.enums import ExperimentStatus
from trafficverse.domain.errors import InvalidStateTransitionError
from trafficverse.domain.state_machine import can_transition, require_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ExperimentStatus.CREATED, ExperimentStatus.PREPARING),
        (ExperimentStatus.PREPARING, ExperimentStatus.READY),
        (ExperimentStatus.READY, ExperimentStatus.RUNNING),
        (ExperimentStatus.RUNNING, ExperimentStatus.PAUSED),
        (ExperimentStatus.PAUSED, ExperimentStatus.RUNNING),
        (ExperimentStatus.RUNNING, ExperimentStatus.STOPPING),
        (ExperimentStatus.STOPPING, ExperimentStatus.COMPLETED),
    ],
)
def test_lifecycle_transition_is_allowed(
    current: ExperimentStatus,
    target: ExperimentStatus,
) -> None:
    assert can_transition(current, target)
    require_transition(current, target)


def test_self_transition_is_idempotent() -> None:
    assert can_transition(ExperimentStatus.RUNNING, ExperimentStatus.RUNNING)


def test_created_cannot_jump_directly_to_running() -> None:
    with pytest.raises(InvalidStateTransitionError) as captured:
        require_transition(ExperimentStatus.CREATED, ExperimentStatus.RUNNING)

    assert captured.value.details == {"current": "CREATED", "target": "RUNNING"}
