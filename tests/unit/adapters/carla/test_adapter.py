from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from trafficverse.adapters.carla import CarlaAdapter
from trafficverse.adapters.carla.models import (
    RuntimeOperationResult,
    RuntimeSpawnRequest,
    RuntimeSpawnResult,
    RuntimeTrafficLight,
    RuntimeTransform,
    RuntimeVersions,
    RuntimeWorldSettings,
)
from trafficverse.config.models import CarlaConfig, WeatherConfig
from trafficverse.domain.enums import ErrorCode, RequirementMode, TrafficLightColor
from trafficverse.domain.errors import TrafficVerseError
from trafficverse.domain.models import TrafficLightUpdate, Vector3


class FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.versions = RuntimeVersions("0.9.16", "0.9.16")
        self.settings = RuntimeWorldSettings(False, None)
        self.ignore_settings = False
        self.actors: set[int] = set()
        self.next_actor_id = 100
        self.spawn_failures: dict[str, int] = {}
        self.spawn_batches: list[tuple[str, ...]] = []
        self.frame = 0
        self.frozen = False
        self.light_colors: list[TrafficLightColor] = []

    def connect(
        self, host: str, port: int, timeout_s: float, worker_threads: int
    ) -> RuntimeVersions:
        self.calls.append(f"connect:{host}:{port}:{timeout_s}:{worker_threads}")
        return self.versions

    def load_world(self, map_name: str) -> None:
        self.calls.append(f"load_world:{map_name}")

    def get_world_settings(self) -> RuntimeWorldSettings:
        self.calls.append("get_world_settings")
        return self.settings

    def apply_world_settings(self, settings: RuntimeWorldSettings) -> None:
        self.calls.append(
            f"apply_settings:{settings.synchronous_mode}:{settings.fixed_delta_seconds}"
        )
        if not self.ignore_settings:
            self.settings = settings

    def set_weather(self, preset: str) -> None:
        self.calls.append(f"set_weather:{preset}")

    def available_blueprints(self, pattern: str) -> tuple[str, ...]:
        self.calls.append(f"blueprints:{pattern}")
        return ("vehicle.audi.tt", "vehicle.tesla.model3")

    def spawn_vehicles(
        self, requests: Sequence[RuntimeSpawnRequest]
    ) -> tuple[RuntimeSpawnResult, ...]:
        batch = tuple(request.vehicle_id for request in requests)
        self.spawn_batches.append(batch)
        self.calls.append(f"spawn:{','.join(batch)}")
        results = []
        for request in requests:
            failures = self.spawn_failures.get(request.vehicle_id, 0)
            if failures > 0:
                self.spawn_failures[request.vehicle_id] = failures - 1
                results.append(RuntimeSpawnResult(request.vehicle_id, error="collision"))
            else:
                actor_id = self.next_actor_id
                self.next_actor_id += 1
                self.actors.add(actor_id)
                results.append(RuntimeSpawnResult(request.vehicle_id, actor_id=actor_id))
        return tuple(results)

    def update_actors(
        self, updates: Sequence[tuple[int, RuntimeTransform]]
    ) -> tuple[RuntimeOperationResult, ...]:
        self.calls.append(f"update:{len(updates)}")
        return tuple(RuntimeOperationResult(actor_id) for actor_id, _ in updates)

    def destroy_actors(self, actor_ids: Sequence[int]) -> tuple[RuntimeOperationResult, ...]:
        self.calls.append(f"destroy:{','.join(str(actor_id) for actor_id in actor_ids)}")
        self.actors.difference_update(actor_ids)
        return tuple(RuntimeOperationResult(actor_id) for actor_id in actor_ids)

    def existing_actor_ids(self, actor_ids: Sequence[int]) -> frozenset[int]:
        return frozenset(set(actor_ids) & self.actors)

    def freeze_traffic_lights(self, frozen: bool) -> None:
        self.calls.append(f"freeze_lights:{frozen}")
        self.frozen = frozen

    def traffic_lights(self) -> tuple[RuntimeTrafficLight, ...]:
        return (RuntimeTrafficLight(42, "1012_0", self.frozen),)

    def update_traffic_lights(
        self, updates: Sequence[tuple[int, TrafficLightColor]]
    ) -> tuple[RuntimeOperationResult, ...]:
        self.light_colors.extend(color for _, color in updates)
        self.calls.append(f"lights:{len(updates)}")
        return tuple(RuntimeOperationResult(actor_id) for actor_id, _ in updates)

    def tick(self, timeout_s: float) -> int:
        self.calls.append(f"tick:{timeout_s}")
        self.frame += 1
        return self.frame

    def actor_count(self) -> int:
        return len(self.actors)

    def disconnect(self) -> None:
        self.calls.append("disconnect")


@dataclass(frozen=True, slots=True)
class Spec:
    vehicle_id: str
    blueprint_id: str
    position: Vector3
    heading_rad: float


def config(**updates: object) -> CarlaConfig:
    values: dict[str, object] = {
        "mode": RequirementMode.REQUIRED,
        "host": "carla.internal",
        "port": 2000,
        "timeout_s": 30.0,
        "expected_version": "0.9.16",
        "step_ms": 50,
        "spawn_retries": 2,
    }
    values.update(updates)
    return CarlaConfig.model_validate(values)


def spec(vehicle_id: str, blueprint: str = "vehicle.unknown") -> Spec:
    return Spec(vehicle_id, blueprint, Vector3(x=1.0, y=2.0, z=0.5), 0.25)


def loaded_adapter(runtime: FakeRuntime) -> CarlaAdapter:
    adapter = CarlaAdapter(runtime)
    adapter.connect(config())
    adapter.load_world("Town04", WeatherConfig(preset="ClearNoon"))
    return adapter


def test_lifecycle_call_order_and_cleanup_restores_settings() -> None:
    runtime = FakeRuntime()
    adapter = loaded_adapter(runtime)
    actor_id = adapter.spawn_vehicle(spec("v-1"))

    adapter.close()

    assert actor_id == 100
    assert runtime.actors == set()
    assert runtime.settings == RuntimeWorldSettings(False, None)
    assert runtime.calls == [
        "connect:carla.internal:2000:30.0:0",
        "load_world:Town04",
        "get_world_settings",
        "apply_settings:True:0.05",
        "get_world_settings",
        "set_weather:ClearNoon",
        "freeze_lights:True",
        "blueprints:vehicle.*",
        "spawn:v-1",
        "destroy:100",
        "freeze_lights:False",
        "apply_settings:False:None",
        "disconnect",
    ]


@pytest.mark.parametrize(
    "versions",
    [
        RuntimeVersions("0.9.15", "0.9.16"),
        RuntimeVersions("0.9.16", "0.9.15"),
    ],
)
def test_version_mismatch_has_stable_error(versions: RuntimeVersions) -> None:
    runtime = FakeRuntime()
    runtime.versions = versions
    adapter = CarlaAdapter(runtime)

    with pytest.raises(TrafficVerseError) as raised:
        adapter.connect(config())

    assert raised.value.code is ErrorCode.CARLA_VERSION_MISMATCH
    assert runtime.calls[-1] == "disconnect"


def test_sync_settings_are_verified_after_application() -> None:
    runtime = FakeRuntime()
    runtime.ignore_settings = True
    adapter = CarlaAdapter(runtime)
    adapter.connect(config())

    with pytest.raises(TrafficVerseError) as raised:
        adapter.load_world("Town04", WeatherConfig(preset="ClearNoon"))

    assert raised.value.code is ErrorCode.CARLA_SYNC_MISMATCH
    adapter.close()
    assert runtime.settings == RuntimeWorldSettings(False, None)


def test_tick_rejects_target_time_that_skips_fixed_step() -> None:
    runtime = FakeRuntime()
    adapter = loaded_adapter(runtime)

    with pytest.raises(TrafficVerseError) as raised:
        adapter.tick(100)

    assert raised.value.code is ErrorCode.CARLA_SYNC_MISMATCH
    assert runtime.frame == 0
    adapter.close()


def test_partial_spawn_failure_retries_only_failed_vehicle() -> None:
    runtime = FakeRuntime()
    runtime.spawn_failures["v-2"] = 1
    adapter = loaded_adapter(runtime)

    results = adapter.spawn_vehicles((spec("v-2"), spec("v-1", "vehicle.audi.tt")))

    assert [result.success for result in results] == [True, True]
    assert runtime.spawn_batches == [("v-1", "v-2"), ("v-2",)]
    assert results[0].actor_id == 101
    assert results[1].actor_id == 100
    adapter.close()


def test_external_actor_loss_is_removed_from_adapter_ownership() -> None:
    runtime = FakeRuntime()
    adapter = loaded_adapter(runtime)
    actor_id = adapter.spawn_vehicle(spec("v-1"))
    runtime.actors.remove(actor_id)

    assert adapter.existing_actor_ids((actor_id,)) == frozenset()
    assert adapter.diagnostics().owned_actor_count == 0

    adapter.close()
    assert f"destroy:{actor_id}" not in runtime.calls


def test_traffic_lights_are_frozen_and_accept_three_colors() -> None:
    runtime = FakeRuntime()
    adapter = loaded_adapter(runtime)
    light = adapter.traffic_lights()[0]
    for color in (
        TrafficLightColor.RED,
        TrafficLightColor.YELLOW,
        TrafficLightColor.GREEN,
    ):
        adapter.update_traffic_lights(
            (TrafficLightUpdate(carla_actor_id=light.actor_id, color=color),)
        )

    assert light.frozen
    assert runtime.light_colors == [
        TrafficLightColor.RED,
        TrafficLightColor.YELLOW,
        TrafficLightColor.GREEN,
    ]
    adapter.close()
