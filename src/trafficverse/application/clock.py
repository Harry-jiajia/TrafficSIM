"""Deterministic simulation clock independent from wall time."""

import math

from trafficverse.domain.enums import ErrorCode
from trafficverse.domain.errors import TrafficVerseError

_SUPPORTED_SPEEDS = (0.5, 1.0, 2.0)


class SimulationClock:
    def __init__(
        self,
        step_ms: int,
        *,
        initial_time_ms: int = 0,
        speed_multiplier: float = 1.0,
    ) -> None:
        if step_ms <= 0:
            raise ValueError("step_ms must be greater than zero")
        if initial_time_ms < 0:
            raise ValueError("initial_time_ms must not be negative")
        self._step_ms = step_ms
        self._current_time_ms = initial_time_ms
        self._speed_multiplier = 1.0
        self.set_speed(speed_multiplier)

    @property
    def step_ms(self) -> int:
        return self._step_ms

    @property
    def current_time_ms(self) -> int:
        return self._current_time_ms

    @property
    def speed_multiplier(self) -> float:
        return self._speed_multiplier

    @property
    def next_time_ms(self) -> int:
        return self._current_time_ms + self._step_ms

    @property
    def wall_interval_s(self) -> float:
        return self._step_ms / 1000.0 / self._speed_multiplier

    def commit(self, simulation_time_ms: int) -> None:
        if simulation_time_ms != self.next_time_ms:
            raise TrafficVerseError(
                ErrorCode.INVALID_STATE_TRANSITION,
                "simulation clock can only advance by one fixed step",
                details={
                    "expected_ms": str(self.next_time_ms),
                    "actual_ms": str(simulation_time_ms),
                },
            )
        self._current_time_ms = simulation_time_ms

    def set_speed(self, multiplier: float) -> None:
        if not any(math.isclose(multiplier, value) for value in _SUPPORTED_SPEEDS):
            raise ValueError("speed multiplier must be one of 0.5, 1.0, or 2.0")
        self._speed_multiplier = multiplier
