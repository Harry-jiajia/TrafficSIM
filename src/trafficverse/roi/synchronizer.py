"""ROI hysteresis and one-to-one vehicle/actor reconciliation."""

from __future__ import annotations

import math
from dataclasses import dataclass

from trafficverse.domain.models import TrafficSnapshot, VehicleState
from trafficverse.roi.coordinate_transformer import CoordinateTransformer
from trafficverse.roi.models import (
    RoiApplyPlan,
    RoiApplyResult,
    RoiDefinition,
    VehicleActorTransform,
    VehicleBinding,
    VehicleRenderSpec,
)


@dataclass(frozen=True, slots=True)
class _RetryState:
    failures: int
    retry_at_sequence: int


class RoiSynchronizer:
    """Stateful bookkeeping around a side-effect-free reconciliation plan."""

    def __init__(
        self,
        definition: RoiDefinition,
        transformer: CoordinateTransformer,
        *,
        blueprint_id: str = "vehicle.tesla.model3",
        retry_base_ticks: int = 1,
        retry_max_ticks: int = 32,
    ) -> None:
        if retry_base_ticks <= 0 or retry_max_ticks < retry_base_ticks:
            raise ValueError("invalid ROI spawn retry configuration")
        self._definition = definition
        self._transformer = transformer
        self._blueprint_id = blueprint_id
        self._retry_base_ticks = retry_base_ticks
        self._retry_max_ticks = retry_max_ticks
        self._by_vehicle: dict[str, VehicleBinding] = {}
        self._by_actor: dict[int, str] = {}
        self._retry: dict[str, _RetryState] = {}

    @property
    def bindings(self) -> tuple[VehicleBinding, ...]:
        return tuple(self._by_vehicle[key] for key in sorted(self._by_vehicle))

    def actor_ids(self) -> frozenset[int]:
        return frozenset(self._by_actor)

    def report_missing_actor_ids(self, actor_ids: frozenset[int]) -> None:
        for actor_id in actor_ids:
            vehicle_id = self._by_actor.pop(actor_id, None)
            if vehicle_id is not None:
                self._by_vehicle.pop(vehicle_id, None)
                self._retry.pop(vehicle_id, None)

    def plan(self, snapshot: TrafficSnapshot) -> RoiApplyPlan:
        vehicles = {vehicle.vehicle_id: vehicle for vehicle in snapshot.vehicles}
        focus_x, focus_y = self._resolve_focus(vehicles)
        destroy_pairs = []
        updates = []
        for vehicle_id, binding in sorted(self._by_vehicle.items()):
            vehicle = vehicles.get(vehicle_id)
            if vehicle is None or self._distance(vehicle, focus_x, focus_y) > (
                self._definition.radius_m + self._definition.buffer_m
            ):
                destroy_pairs.append((vehicle_id, binding.actor_id))
                continue
            position = self._transformer.transform_position(vehicle.position)
            updates.append(
                VehicleActorTransform(
                    actor_id=binding.actor_id,
                    position=position,
                    heading_rad=self._transformer.transform_heading(vehicle.heading_rad),
                )
            )

        retained_count = len(self._by_vehicle) - len(destroy_pairs)
        available = max(0, self._definition.max_actors - retained_count)
        candidates = [
            vehicle
            for vehicle_id, vehicle in vehicles.items()
            if vehicle_id not in self._by_vehicle
            and self._distance(vehicle, focus_x, focus_y) <= self._definition.radius_m
            and self._retry_ready(vehicle_id, snapshot.sequence)
        ]
        candidates.sort(
            key=lambda vehicle: (
                0 if self._is_priority(vehicle.vehicle_id) else 1,
                self._distance(vehicle, focus_x, focus_y),
                vehicle.vehicle_id,
            )
        )
        selected, deferred = candidates[:available], candidates[available:]
        spawns = tuple(
            VehicleRenderSpec(
                vehicle_id=vehicle.vehicle_id,
                blueprint_id=self._blueprint_id,
                position=self._transformer.transform_position(vehicle.position),
                heading_rad=self._transformer.transform_heading(vehicle.heading_rad),
            )
            for vehicle in selected
        )
        return RoiApplyPlan(
            sequence=snapshot.sequence,
            simulation_time_ms=snapshot.simulation_time_ms,
            spawns=spawns,
            actor_updates=tuple(updates),
            destroy_actor_ids=tuple(actor_id for _, actor_id in destroy_pairs),
            destroy_vehicle_ids=tuple(vehicle_id for vehicle_id, _ in destroy_pairs),
            degraded_vehicle_ids=tuple(vehicle.vehicle_id for vehicle in deferred),
        )

    def commit(self, result: RoiApplyResult) -> None:
        plan = result.plan
        requested = {spec.vehicle_id for spec in plan.spawns}
        returned = {item.vehicle_id for item in result.spawn_results}
        if requested != returned or len(result.spawn_results) != len(requested):
            raise ValueError("ROI spawn results do not exactly match the plan")
        successful_actor_ids = [item.actor_id for item in result.spawn_results if item.success]
        if len(successful_actor_ids) != len(set(successful_actor_ids)):
            raise ValueError("ROI spawn results contain duplicate actor IDs")
        retained_actor_ids = set(self._by_actor) - set(plan.destroy_actor_ids)
        if retained_actor_ids & set(successful_actor_ids):
            raise ValueError("ROI spawn result reuses an active actor ID")

        for vehicle_id, actor_id in zip(
            plan.destroy_vehicle_ids, plan.destroy_actor_ids, strict=True
        ):
            binding = self._by_vehicle.get(vehicle_id)
            if binding is not None and binding.actor_id == actor_id:
                self._by_vehicle.pop(vehicle_id)
                self._by_actor.pop(actor_id, None)
            self._retry.pop(vehicle_id, None)

        for spawn in result.spawn_results:
            if spawn.success:
                spawned_actor_id = spawn.actor_id
                if spawned_actor_id is None:
                    raise ValueError("successful ROI spawn requires an actor ID")
                if spawn.vehicle_id in self._by_vehicle or spawned_actor_id in self._by_actor:
                    raise ValueError("ROI binding must remain one-to-one")
                binding = VehicleBinding(
                    vehicle_id=spawn.vehicle_id,
                    actor_id=spawned_actor_id,
                    created_at_ms=plan.simulation_time_ms,
                    last_updated_at_ms=plan.simulation_time_ms,
                )
                self._by_vehicle[spawn.vehicle_id] = binding
                self._by_actor[spawned_actor_id] = spawn.vehicle_id
                self._retry.pop(spawn.vehicle_id, None)
            else:
                previous = self._retry.get(spawn.vehicle_id)
                failures = 1 if previous is None else previous.failures + 1
                delay = min(
                    self._retry_max_ticks,
                    self._retry_base_ticks * (2 ** (failures - 1)),
                )
                self._retry[spawn.vehicle_id] = _RetryState(
                    failures=failures,
                    retry_at_sequence=plan.sequence + delay,
                )

        updated_by_actor = {update.actor_id for update in plan.actor_updates}
        for actor_id in updated_by_actor:
            mapped_vehicle_id = self._by_actor.get(actor_id)
            if mapped_vehicle_id is not None:
                binding = self._by_vehicle[mapped_vehicle_id]
                self._by_vehicle[mapped_vehicle_id] = VehicleBinding(
                    vehicle_id=mapped_vehicle_id,
                    actor_id=actor_id,
                    created_at_ms=binding.created_at_ms,
                    last_updated_at_ms=plan.simulation_time_ms,
                )

    def _resolve_focus(self, vehicles: dict[str, VehicleState]) -> tuple[float, float]:
        if self._definition.focus_vehicle_id is not None:
            vehicle = vehicles.get(self._definition.focus_vehicle_id)
            if vehicle is None:
                raise ValueError(
                    f"ROI focus vehicle is absent: {self._definition.focus_vehicle_id}"
                )
            return vehicle.position.x, vehicle.position.y
        assert self._definition.focus_x is not None and self._definition.focus_y is not None
        return self._definition.focus_x, self._definition.focus_y

    def _is_priority(self, vehicle_id: str) -> bool:
        return vehicle_id == self._definition.focus_vehicle_id or (
            vehicle_id in self._definition.priority_vehicle_ids
        )

    def _retry_ready(self, vehicle_id: str, sequence: int) -> bool:
        retry = self._retry.get(vehicle_id)
        return retry is None or sequence >= retry.retry_at_sequence

    @staticmethod
    def _distance(vehicle: VehicleState, focus_x: float, focus_y: float) -> float:
        return math.hypot(vehicle.position.x - focus_x, vehicle.position.y - focus_y)
