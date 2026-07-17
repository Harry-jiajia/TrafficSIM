from __future__ import annotations

import math
from collections.abc import Mapping
from uuid import UUID

import pytest

from trafficverse.adapters.sumo import SumoTrafficEngineAdapter
from trafficverse.adapters.sumo.models import SumoTrafficLightSample, SumoVehicleSample
from trafficverse.config.models import SumoConfig
from trafficverse.domain.enums import ErrorCode, LaneChangeDirection
from trafficverse.domain.errors import TrafficVerseError
from trafficverse.domain.models import ControlCommand


class FakeSumoRuntime:
    def __init__(self) -> None:
        self.version = "1.27.1"
        self.time_s = 0.0
        self.step_calls: list[float] = []
        self.speed_calls: list[tuple[str, float]] = []
        self.acceleration_calls: list[tuple[str, float, float]] = []
        self.lane_calls: list[tuple[str, int, float]] = []
        self.closed = False
        self.connect_error: Exception | None = None
        self.fail_controls_for: set[str] = set()

    def connect(self, config: SumoConfig) -> str:
        del config
        if self.connect_error is not None:
            raise self.connect_error
        return self.version

    def simulation_step(self, target_time_s: float) -> None:
        self.step_calls.append(target_time_s)
        self.time_s = target_time_s

    def simulation_time_s(self) -> float:
        return self.time_s

    def departed_vehicle_ids(self) -> tuple[str, ...]:
        return ("vehicle-1",)

    def arrived_vehicle_ids(self) -> tuple[str, ...]:
        return ()

    def vehicle_samples(self) -> tuple[SumoVehicleSample, ...]:
        return (
            SumoVehicleSample(
                vehicle_id="vehicle-1",
                x_m=10.0,
                y_m=20.0,
                z_m=0.0,
                speed_mps=8.0,
                acceleration_mps2=1.0,
                angle_deg=90.0,
                lane_id="-325_0",
                route_id="route-1",
            ),
        )

    def traffic_light_samples(self) -> tuple[SumoTrafficLightSample, ...]:
        return (SumoTrafficLightSample(signal_id="signal:106_0", phase="GREEN"),)

    def set_vehicle_speed(self, vehicle_id: str, speed_mps: float) -> None:
        self._check_control(vehicle_id)
        self.speed_calls.append((vehicle_id, speed_mps))

    def set_vehicle_acceleration(
        self, vehicle_id: str, acceleration_mps2: float, duration_s: float
    ) -> None:
        self._check_control(vehicle_id)
        self.acceleration_calls.append((vehicle_id, acceleration_mps2, duration_s))

    def change_lane_relative(self, vehicle_id: str, direction: int, duration_s: float) -> None:
        self._check_control(vehicle_id)
        self.lane_calls.append((vehicle_id, direction, duration_s))

    def close(self) -> None:
        self.closed = True

    def _check_control(self, vehicle_id: str) -> None:
        if vehicle_id in self.fail_controls_for:
            raise RuntimeError("vehicle is absent")


def _config(**updates: object) -> SumoConfig:
    payload: dict[str, object] = {
        "config_file": "map.sumocfg",
        "expected_version": "1.27.1",
    }
    payload.update(updates)
    return SumoConfig.model_validate(payload)


def test_step_calls_traci_once_and_normalizes_snapshot() -> None:
    runtime = FakeSumoRuntime()
    adapter = SumoTrafficEngineAdapter(UUID(int=1), runtime)
    adapter.load(_config())

    snapshot = adapter.step(50)

    assert runtime.step_calls == [0.05]
    assert snapshot.simulation_time_ms == 50
    assert snapshot.sequence == 1
    assert snapshot.vehicles[0].vehicle_id == "vehicle-1"
    assert snapshot.vehicles[0].lane_id == "-325_0"
    assert math.isclose(snapshot.vehicles[0].heading_rad, 0.0)
    assert snapshot.traffic_lights[0].signal_id == "signal:106_0"
    assert adapter.diagnostics().departed_vehicle_ids == ("vehicle-1",)


def test_apply_controls_attempts_each_vehicle_and_records_rejections() -> None:
    runtime = FakeSumoRuntime()
    runtime.fail_controls_for.add("missing")
    adapter = SumoTrafficEngineAdapter(UUID(int=2), runtime)
    adapter.load(_config())
    commands: Mapping[str, ControlCommand] = {
        "missing": ControlCommand(desired_speed_mps=3.0),
        "vehicle-1": ControlCommand(
            desired_speed_mps=7.0,
            desired_acceleration_mps2=0.5,
            lane_change=LaneChangeDirection.LEFT,
        ),
    }

    adapter.apply_controls(commands)

    assert runtime.speed_calls == [("vehicle-1", 7.0)]
    assert runtime.acceleration_calls == [("vehicle-1", 0.5, 0.05)]
    assert runtime.lane_calls == [("vehicle-1", 1, 0.05)]
    assert adapter.diagnostics().rejected_control_vehicle_ids == ("missing",)


def test_version_mismatch_closes_connection() -> None:
    runtime = FakeSumoRuntime()
    runtime.version = "1.26.0"
    adapter = SumoTrafficEngineAdapter(UUID(int=3), runtime)

    with pytest.raises(TrafficVerseError) as captured:
        adapter.load(_config())

    assert captured.value.code is ErrorCode.SUMO_VERSION_MISMATCH
    assert runtime.closed


def test_connection_failure_closes_partial_runtime() -> None:
    runtime = FakeSumoRuntime()
    runtime.connect_error = RuntimeError("connection refused")
    adapter = SumoTrafficEngineAdapter(UUID(int=6), runtime)

    with pytest.raises(TrafficVerseError) as captured:
        adapter.load(_config())

    assert captured.value.code is ErrorCode.SUMO_CONNECTION_FAILED
    assert runtime.closed


def test_non_contiguous_target_time_is_rejected_without_step() -> None:
    runtime = FakeSumoRuntime()
    adapter = SumoTrafficEngineAdapter(UUID(int=4), runtime)
    adapter.load(_config())

    with pytest.raises(TrafficVerseError) as captured:
        adapter.step(100)

    assert captured.value.code is ErrorCode.SUMO_TIME_MISMATCH
    assert runtime.step_calls == []


def test_close_is_idempotent() -> None:
    runtime = FakeSumoRuntime()
    adapter = SumoTrafficEngineAdapter(UUID(int=5), runtime)
    adapter.load(_config())

    adapter.close()
    adapter.close()

    assert runtime.closed
