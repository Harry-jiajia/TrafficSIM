"""Pure ROI synchronization plans and state value objects."""

from __future__ import annotations

from dataclasses import dataclass

from trafficverse.domain.models import ActorSpawnResult, Vector3


@dataclass(frozen=True, slots=True)
class RoiDefinition:
    radius_m: float
    buffer_m: float
    max_actors: int
    focus_x: float | None = None
    focus_y: float | None = None
    focus_vehicle_id: str | None = None
    priority_vehicle_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.radius_m <= 0 or self.buffer_m <= 0:
            raise ValueError("ROI radius and buffer must be positive")
        if self.max_actors <= 0:
            raise ValueError("ROI max_actors must be positive")
        fixed = self.focus_x is not None and self.focus_y is not None
        following = self.focus_vehicle_id is not None
        if fixed == following:
            raise ValueError("ROI requires exactly one fixed or follow-vehicle focus")


@dataclass(frozen=True, slots=True)
class VehicleBinding:
    vehicle_id: str
    actor_id: int
    created_at_ms: int
    last_updated_at_ms: int


@dataclass(frozen=True, slots=True)
class VehicleRenderSpec:
    vehicle_id: str
    blueprint_id: str
    position: Vector3
    heading_rad: float


@dataclass(frozen=True, slots=True)
class VehicleActorTransform:
    actor_id: int
    position: Vector3
    heading_rad: float


@dataclass(frozen=True, slots=True)
class RoiApplyPlan:
    sequence: int = 0
    simulation_time_ms: int = 0
    spawns: tuple[VehicleRenderSpec, ...] = ()
    actor_updates: tuple[VehicleActorTransform, ...] = ()
    destroy_actor_ids: tuple[int, ...] = ()
    destroy_vehicle_ids: tuple[str, ...] = ()
    degraded_vehicle_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.sequence < 0 or self.simulation_time_ms < 0:
            raise ValueError("ROI plan time and sequence must be non-negative")
        spawn_ids = [item.vehicle_id for item in self.spawns]
        if len(spawn_ids) != len(set(spawn_ids)):
            raise ValueError("ROI plan contains duplicate spawn vehicle IDs")
        if len(self.destroy_actor_ids) != len(set(self.destroy_actor_ids)):
            raise ValueError("ROI plan contains duplicate destroy actor IDs")
        if set(spawn_ids) & set(self.destroy_vehicle_ids):
            raise ValueError("ROI plan cannot spawn and destroy the same vehicle")
        if len(self.destroy_actor_ids) != len(self.destroy_vehicle_ids):
            raise ValueError("ROI destroy actor and vehicle IDs must have equal length")


@dataclass(frozen=True, slots=True)
class RoiApplyResult:
    plan: RoiApplyPlan
    spawn_results: tuple[ActorSpawnResult, ...] = ()
