"""Typed internal boundary between the CARLA adapter and the SDK wrapper."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from trafficverse.domain.enums import TrafficLightColor


@dataclass(frozen=True, slots=True)
class RuntimeVersions:
    client: str
    server: str


@dataclass(frozen=True, slots=True)
class RuntimeWorldSettings:
    synchronous_mode: bool
    fixed_delta_seconds: float | None


@dataclass(frozen=True, slots=True)
class RuntimeTransform:
    x: float
    y: float
    z: float
    heading_rad: float


@dataclass(frozen=True, slots=True)
class RuntimeSpawnRequest:
    vehicle_id: str
    blueprint_id: str
    transform: RuntimeTransform


@dataclass(frozen=True, slots=True)
class RuntimeSpawnResult:
    vehicle_id: str
    actor_id: int | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeOperationResult:
    actor_id: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeTrafficLight:
    actor_id: int
    opendrive_id: str
    frozen: bool


@dataclass(frozen=True, slots=True)
class RuntimeCameraFrame:
    camera_id: str
    carla_frame: int
    simulation_time_ms: int
    width: int
    height: int
    jpeg_bytes: bytes


CameraCallback = Callable[[RuntimeCameraFrame], None]


class CarlaRuntime(Protocol):
    """Small typed facade; concrete SDK objects never cross this boundary."""

    def connect(
        self, host: str, port: int, timeout_s: float, worker_threads: int
    ) -> RuntimeVersions: ...

    def load_world(self, map_name: str) -> None: ...

    def get_world_settings(self) -> RuntimeWorldSettings: ...

    def apply_world_settings(self, settings: RuntimeWorldSettings) -> None: ...

    def set_weather(self, preset: str) -> None: ...

    def available_blueprints(self, pattern: str) -> tuple[str, ...]: ...

    def spawn_vehicles(
        self, requests: Sequence[RuntimeSpawnRequest]
    ) -> tuple[RuntimeSpawnResult, ...]: ...

    def update_actors(
        self, updates: Sequence[tuple[int, RuntimeTransform]]
    ) -> tuple[RuntimeOperationResult, ...]: ...

    def destroy_actors(self, actor_ids: Sequence[int]) -> tuple[RuntimeOperationResult, ...]: ...

    def existing_actor_ids(self, actor_ids: Sequence[int]) -> frozenset[int]: ...

    def freeze_traffic_lights(self, frozen: bool) -> None: ...

    def traffic_lights(self) -> tuple[RuntimeTrafficLight, ...]: ...

    def update_traffic_lights(
        self, updates: Sequence[tuple[int, TrafficLightColor]]
    ) -> tuple[RuntimeOperationResult, ...]: ...

    def start_camera(
        self,
        *,
        mode: str,
        target_actor_id: int | None,
        width: int,
        height: int,
        fps: int,
        jpeg_quality: int,
        callback: CameraCallback,
    ) -> None: ...

    def stop_camera(self) -> None: ...

    def tick(self, timeout_s: float) -> int: ...

    def actor_count(self) -> int: ...

    def disconnect(self) -> None: ...
