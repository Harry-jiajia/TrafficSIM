"""Simulation engine ports; no third-party SDK types may appear here."""

from collections.abc import Mapping, Sequence
from typing import Protocol

from trafficverse.config.models import CarlaConfig, TrafficEngineConfig, WeatherConfig
from trafficverse.domain.models import (
    ActorSpawnResult,
    CameraCommand,
    CameraFrame,
    CarlaFrame,
    CarlaTrafficLight,
    ComponentHealth,
    ControlCommand,
    TrafficLightUpdate,
    TrafficSnapshot,
    Vector3,
)


class RenderVehicleSpec(Protocol):
    @property
    def vehicle_id(self) -> str: ...

    @property
    def blueprint_id(self) -> str: ...

    @property
    def position(self) -> Vector3: ...

    @property
    def heading_rad(self) -> float: ...


class ActorTransform(Protocol):
    @property
    def actor_id(self) -> int: ...

    @property
    def position(self) -> Vector3: ...

    @property
    def heading_rad(self) -> float: ...


class TrafficEnginePort(Protocol):
    def load(self, config: TrafficEngineConfig) -> None: ...

    def apply_controls(self, commands: Mapping[str, ControlCommand]) -> None: ...

    def step(self, target_time_ms: int) -> TrafficSnapshot: ...

    def health(self) -> ComponentHealth: ...

    def close(self) -> None: ...


class CarlaPort(Protocol):
    def connect(self, config: CarlaConfig) -> None: ...

    def load_world(self, map_name: str, weather: WeatherConfig) -> None: ...

    def spawn_vehicle(self, spec: RenderVehicleSpec) -> int: ...

    def spawn_vehicles(
        self, specs: Sequence[RenderVehicleSpec]
    ) -> tuple[ActorSpawnResult, ...]: ...

    def update_actors(self, updates: Sequence[ActorTransform]) -> None: ...

    def destroy_actors(self, actor_ids: Sequence[int]) -> None: ...

    def existing_actor_ids(self, actor_ids: Sequence[int]) -> frozenset[int]: ...

    def traffic_lights(self) -> tuple[CarlaTrafficLight, ...]: ...

    def update_traffic_lights(self, updates: Sequence[TrafficLightUpdate]) -> None: ...

    def tick(self, target_time_ms: int) -> CarlaFrame: ...

    def latest_camera_frame(self) -> CameraFrame | None: ...

    def set_camera(self, command: CameraCommand) -> None: ...

    def health(self) -> ComponentHealth: ...

    def close(self) -> None: ...
