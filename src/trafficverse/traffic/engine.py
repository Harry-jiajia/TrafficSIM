"""Fixed-step, two-phase native traffic engine for the demonstration MVP."""

import bisect
import math
import time
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar, cast
from uuid import UUID

import yaml
from pydantic import BaseModel, ValidationError

from trafficverse.config.models import TrafficBehaviorConfig, TrafficEngineConfig
from trafficverse.domain.enums import (
    AutomationLevel,
    ComponentStatus,
    LaneChangeDirection,
    TrafficLightColor,
    VehicleAction,
)
from trafficverse.domain.models import (
    ComponentHealth,
    ControlCommand,
    TrafficLightState,
    TrafficSnapshot,
    Vector3,
    VehicleState,
)
from trafficverse.domain.models.common import StrictModel
from trafficverse.maps.models import NETWORK_SCHEMA_VERSION, Lane, LaneLink, RoadNetwork
from trafficverse.maps.validation import load_network, route_is_reachable, validate_network
from trafficverse.traffic.models import RouteCatalog, RouteDemand, SignalCatalog, SignalProgram

ModelT = TypeVar("ModelT", bound=BaseModel)


class TrafficEngineDiagnostics(StrictModel):
    sequence: int
    simulation_time_ms: int
    active_vehicles: int
    arrived_vehicles: int
    rejected_controls: int
    completed_lane_changes: int
    last_step_duration_ms: float
    p95_step_duration_ms: float
    maximum_step_duration_ms: float


@dataclass(slots=True)
class _Vehicle:
    demand: RouteDemand
    route: list[str]
    route_index: int
    lane_id: str
    s_m: float
    speed_mps: float
    acceleration_mps2: float = 0.0
    action: VehicleAction = VehicleAction.KEEP_LANE


@dataclass(frozen=True, slots=True)
class _Proposal:
    lane_id: str
    route_index: int
    s_m: float
    speed_mps: float
    acceleration_mps2: float
    action: VehicleAction


def _load_yaml(path: Path, model: type[ModelT]) -> ModelT:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return model.model_validate(payload)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise ValueError(f"invalid traffic asset {path}: {error}") from error


class NativeTrafficEngine:
    """Deterministic traffic truth source with no external simulator dependency."""

    VERSION = "1.0.0"

    def __init__(self, experiment_id: UUID) -> None:
        self._experiment_id = experiment_id
        self._config: TrafficEngineConfig | None = None
        self._behavior = TrafficBehaviorConfig()
        self._network: RoadNetwork | None = None
        self._lanes: dict[str, Lane] = {}
        self._links: dict[tuple[str, str], LaneLink] = {}
        self._programs: dict[str, SignalProgram] = {}
        self._demands: tuple[RouteDemand, ...] = ()
        self._spawned: set[str] = set()
        self._vehicles: dict[str, _Vehicle] = {}
        self._pending_controls: dict[str, ControlCommand] = {}
        self._sequence = 0
        self._simulation_time_ms = 0
        self._arrived = 0
        self._rejected_controls = 0
        self._completed_lane_changes = 0
        self._last_step_duration_ms = 0.0
        self._maximum_step_duration_ms = 0.0
        self._step_durations_ms: list[float] = []
        self._closed = False

    def load(self, config: TrafficEngineConfig) -> None:
        if self._network is not None and not self._closed:
            raise ValueError("traffic engine is already loaded")
        network = load_network(Path(config.network_path))
        if network.schema_version != config.network_schema_version:
            raise ValueError(
                f"expected {config.network_schema_version}, found {network.schema_version}"
            )
        validate_network(network)
        routes = _load_yaml(Path(config.routes_path), RouteCatalog)
        signals = _load_yaml(Path(config.signals_path), SignalCatalog)
        for route in routes.routes:
            if not route_is_reachable(network, route.lane_ids):
                raise ValueError(f"route {route.route_id} is not reachable")
        network_signals = {signal.signal_id for signal in network.signals}
        configured_signals = {program.signal_id for program in signals.programs}
        unknown = configured_signals - network_signals
        if unknown:
            raise ValueError(f"signal programs reference unknown signals: {sorted(unknown)}")
        self._config = config
        self._behavior = config.behavior
        self._network = network
        self._lanes = {lane.lane_id: lane for lane in network.lanes}
        self._links = {(link.from_lane_id, link.to_lane_id): link for link in network.links}
        self._programs = {program.signal_id: program for program in signals.programs}
        self._demands = tuple(
            sorted(routes.routes, key=lambda item: (item.depart_ms, item.vehicle_id))
        )
        self._spawned.clear()
        self._vehicles.clear()
        self._pending_controls.clear()
        self._sequence = 0
        self._simulation_time_ms = 0
        self._arrived = 0
        self._rejected_controls = 0
        self._completed_lane_changes = 0
        self._last_step_duration_ms = 0.0
        self._maximum_step_duration_ms = 0.0
        self._step_durations_ms.clear()
        self._closed = False

    def apply_controls(self, commands: Mapping[str, ControlCommand]) -> None:
        self._require_loaded()
        self._pending_controls = dict(commands)

    def step(self, target_time_ms: int) -> TrafficSnapshot:
        config = self._require_loaded()
        expected = self._simulation_time_ms + config.step_ms
        if target_time_ms != expected:
            raise ValueError(f"target time must increase by exactly {config.step_ms} ms")
        started = time.perf_counter()
        self._spawn_due(target_time_ms)
        lane_index = self._lane_index()
        controls: dict[str, ControlCommand] = {}
        for vehicle_id, command in sorted(self._pending_controls.items()):
            if vehicle_id in self._vehicles:
                controls[vehicle_id] = command
            else:
                self._rejected_controls += 1
        self._pending_controls.clear()
        proposals = {
            vehicle_id: self._propose(vehicle, lane_index, controls.get(vehicle_id), target_time_ms)
            for vehicle_id, vehicle in sorted(self._vehicles.items())
        }
        self._commit(proposals)
        self._simulation_time_ms = target_time_ms
        self._sequence += 1
        self._assert_safety()
        self._last_step_duration_ms = (time.perf_counter() - started) * 1000.0
        self._maximum_step_duration_ms = max(
            self._maximum_step_duration_ms, self._last_step_duration_ms
        )
        self._step_durations_ms.append(self._last_step_duration_ms)
        return TrafficSnapshot(
            experiment_id=self._experiment_id,
            simulation_time_ms=target_time_ms,
            sequence=self._sequence,
            vehicles=tuple(
                self._vehicle_state(vehicle) for _, vehicle in sorted(self._vehicles.items())
            ),
            traffic_lights=tuple(self._traffic_light_states(target_time_ms)),
        )

    def health(self) -> ComponentHealth:
        status = (
            ComponentStatus.HEALTHY
            if self._network is not None and not self._closed
            else ComponentStatus.UNAVAILABLE
        )
        return ComponentHealth(
            component="traffic-engine",
            status=status,
            version=f"{self.VERSION}/{NETWORK_SCHEMA_VERSION}",
        )

    def diagnostics(self) -> TrafficEngineDiagnostics:
        ordered_durations = sorted(self._step_durations_ms)
        p95_index = max(0, math.ceil(len(ordered_durations) * 0.95) - 1)
        return TrafficEngineDiagnostics(
            sequence=self._sequence,
            simulation_time_ms=self._simulation_time_ms,
            active_vehicles=len(self._vehicles),
            arrived_vehicles=self._arrived,
            rejected_controls=self._rejected_controls,
            completed_lane_changes=self._completed_lane_changes,
            last_step_duration_ms=self._last_step_duration_ms,
            p95_step_duration_ms=(ordered_durations[p95_index] if ordered_durations else 0.0),
            maximum_step_duration_ms=self._maximum_step_duration_ms,
        )

    def close(self) -> None:
        self._vehicles.clear()
        self._pending_controls.clear()
        self._closed = True

    def _require_loaded(self) -> TrafficEngineConfig:
        if self._config is None or self._network is None or self._closed:
            raise RuntimeError("traffic engine is not loaded")
        return self._config

    def _spawn_due(self, target_time_ms: int) -> None:
        occupied = self._lane_index()
        minimum = self._behavior.vehicle_length_m + self._behavior.minimum_gap_m
        for demand in self._demands:
            if demand.depart_ms > target_time_ms or demand.vehicle_id in self._spawned:
                continue
            first_lane = demand.lane_ids[0]
            first_position = occupied[first_lane][0][0] if occupied[first_lane] else math.inf
            if first_position < minimum:
                continue
            vehicle = _Vehicle(demand, list(demand.lane_ids), 0, first_lane, 0.0, 0.0)
            self._vehicles[demand.vehicle_id] = vehicle
            self._spawned.add(demand.vehicle_id)
            bisect.insort(occupied[first_lane], (0.0, demand.vehicle_id))

    def _lane_index(self) -> dict[str, list[tuple[float, str]]]:
        index: dict[str, list[tuple[float, str]]] = defaultdict(list)
        for vehicle_id, vehicle in self._vehicles.items():
            index[vehicle.lane_id].append((vehicle.s_m, vehicle_id))
        for vehicles in index.values():
            vehicles.sort()
        return index

    def _propose(
        self,
        vehicle: _Vehicle,
        lane_index: dict[str, list[tuple[float, str]]],
        command: ControlCommand | None,
        target_time_ms: int,
    ) -> _Proposal:
        config = cast(TrafficEngineConfig, self._config)
        dt = config.step_ms / 1000.0
        lane_id = vehicle.lane_id
        route_index = vehicle.route_index
        action = VehicleAction.KEEP_LANE
        if command is not None and command.lane_change is not LaneChangeDirection.NONE:
            candidate = (
                self._lanes[lane_id].left_lane_id
                if command.lane_change is LaneChangeDirection.LEFT
                else self._lanes[lane_id].right_lane_id
            )
            if candidate is not None and self._lane_change_safe(candidate, vehicle.s_m, lane_index):
                lane_id = candidate
                vehicle.route[route_index] = candidate
                action = (
                    VehicleAction.LANE_CHANGE_LEFT
                    if command.lane_change is LaneChangeDirection.LEFT
                    else VehicleAction.LANE_CHANGE_RIGHT
                )
                self._completed_lane_changes += 1
            else:
                self._rejected_controls += 1
        desired = min(vehicle.demand.desired_speed_mps, self._lanes[lane_id].speed_limit_mps)
        if command is not None and command.desired_speed_mps is not None:
            desired = min(command.desired_speed_mps, self._lanes[lane_id].speed_limit_mps)
        acceleration = min(
            self._behavior.max_acceleration_mps2,
            max(-self._behavior.comfortable_deceleration_mps2, (desired - vehicle.speed_mps) / dt),
        )
        if command is not None and command.desired_acceleration_mps2 is not None:
            acceleration = min(
                self._behavior.max_acceleration_mps2,
                max(-self._behavior.emergency_deceleration_mps2, command.desired_acceleration_mps2),
            )
        if command is not None and command.stop_requested:
            acceleration = -self._behavior.emergency_deceleration_mps2
        obstacle_s = self._obstacle_s(vehicle, lane_id, lane_index, target_time_ms)
        if obstacle_s is not None:
            available = max(0.0, obstacle_s - vehicle.s_m - self._behavior.minimum_gap_m)
            safe_speed = available / self._behavior.time_headway_s
            acceleration = min(acceleration, (safe_speed - vehicle.speed_mps) / dt)
            acceleration = max(-self._behavior.emergency_deceleration_mps2, acceleration)
        speed = max(0.0, vehicle.speed_mps + acceleration * dt)
        position = max(0.0, vehicle.s_m + vehicle.speed_mps * dt + 0.5 * acceleration * dt**2)
        if obstacle_s is not None:
            stopping_position = max(0.0, obstacle_s - self._behavior.minimum_gap_m)
            if position > stopping_position:
                position = stopping_position
                speed = 0.0
                acceleration = -min(
                    self._behavior.emergency_deceleration_mps2,
                    vehicle.speed_mps / dt,
                )
        if speed < 0.05 and acceleration < 0:
            action = VehicleAction.STOP
        elif action is VehicleAction.KEEP_LANE:
            action = (
                VehicleAction.ACCELERATE
                if acceleration > 0.05
                else (VehicleAction.BRAKE if acceleration < -0.05 else VehicleAction.KEEP_LANE)
            )
        return _Proposal(lane_id, route_index, position, speed, acceleration, action)

    def _obstacle_s(
        self,
        vehicle: _Vehicle,
        lane_id: str,
        lane_index: dict[str, list[tuple[float, str]]],
        target_time_ms: int,
    ) -> float | None:
        positions = lane_index[lane_id]
        offset = bisect.bisect_right(positions, (vehicle.s_m, vehicle.demand.vehicle_id))
        leader = (
            positions[offset][0] - self._behavior.vehicle_length_m
            if offset < len(positions)
            else None
        )
        next_lane = (
            vehicle.route[vehicle.route_index + 1]
            if vehicle.route_index + 1 < len(vehicle.route)
            else None
        )
        if next_lane is not None:
            link = self._links.get((lane_id, next_lane))
            if link is not None and link.signal_id is not None:
                color, _ = self._signal_state(link.signal_id, target_time_ms)
                if color in {TrafficLightColor.RED, TrafficLightColor.YELLOW}:
                    stop_line = link.stop_line_s_m or self._lanes[lane_id].length_m
                    leader = stop_line if leader is None else min(leader, stop_line)
        return leader

    def _lane_change_safe(
        self,
        target_lane: str,
        position: float,
        lane_index: dict[str, list[tuple[float, str]]],
    ) -> bool:
        target = lane_index[target_lane]
        offset = bisect.bisect_left(target, (position, ""))
        rear_gap = position - target[offset - 1][0] if offset > 0 else math.inf
        front_gap = target[offset][0] - position if offset < len(target) else math.inf
        return (
            rear_gap >= self._behavior.lane_change_rear_gap_m
            and front_gap >= self._behavior.lane_change_front_gap_m
        )

    def _commit(self, proposals: dict[str, _Proposal]) -> None:
        config = cast(TrafficEngineConfig, self._config)
        dt = config.step_ms / 1000.0
        grouped: dict[str, list[tuple[float, str]]] = defaultdict(list)
        for vehicle_id, proposal in proposals.items():
            grouped[proposal.lane_id].append((proposal.s_m, vehicle_id))
        adjusted = dict(proposals)
        clearance = self._behavior.vehicle_length_m + self._behavior.minimum_gap_m
        for items in grouped.values():
            items.sort(reverse=True)
            leader_position = math.inf
            for proposed_position, vehicle_id in items:
                safe_position = min(proposed_position, leader_position - clearance)
                safe_position = max(0.0, safe_position)
                proposal = adjusted[vehicle_id]
                if safe_position < proposed_position:
                    old_speed = self._vehicles[vehicle_id].speed_mps
                    speed = max(0.0, (safe_position - self._vehicles[vehicle_id].s_m) / dt)
                    adjusted[vehicle_id] = _Proposal(
                        proposal.lane_id,
                        proposal.route_index,
                        safe_position,
                        speed,
                        (speed - old_speed) / dt,
                        VehicleAction.BRAKE if speed > 0 else VehicleAction.STOP,
                    )
                leader_position = safe_position
        arrived: list[str] = []
        for vehicle_id, proposal in sorted(adjusted.items()):
            vehicle = self._vehicles[vehicle_id]
            lane_id, route_index, position = proposal.lane_id, proposal.route_index, proposal.s_m
            while position >= self._lanes[lane_id].length_m:
                position -= self._lanes[lane_id].length_m
                if route_index + 1 >= len(vehicle.route):
                    arrived.append(vehicle_id)
                    break
                candidate = vehicle.route[route_index + 1]
                if candidate not in self._lanes[lane_id].successor_ids:
                    successors = self._lanes[lane_id].successor_ids
                    if not successors:
                        arrived.append(vehicle_id)
                        break
                    candidate = successors[0]
                    vehicle.route[route_index + 1] = candidate
                lane_id = candidate
                route_index += 1
            if vehicle_id in arrived:
                continue
            vehicle.lane_id = lane_id
            vehicle.route_index = route_index
            vehicle.s_m = position
            vehicle.speed_mps = proposal.speed_mps
            vehicle.acceleration_mps2 = proposal.acceleration_mps2
            vehicle.action = proposal.action
        for vehicle_id in arrived:
            del self._vehicles[vehicle_id]
            self._arrived += 1

    def _assert_safety(self) -> None:
        for lane_id, vehicles in self._lane_index().items():
            for (rear_s, rear_id), (front_s, front_id) in zip(vehicles, vehicles[1:], strict=False):
                if front_s - rear_s < (
                    self._behavior.vehicle_length_m + self._behavior.minimum_gap_m - 1e-6
                ):
                    raise RuntimeError(
                        f"collision invariant violated on {lane_id}: {rear_id}/{front_id}"
                    )
        if any(vehicle.s_m < 0 or vehicle.speed_mps < 0 for vehicle in self._vehicles.values()):
            raise RuntimeError("negative traffic state invariant violated")

    def _signal_state(self, signal_id: str, time_ms: int) -> tuple[TrafficLightColor, int]:
        program = self._programs.get(signal_id)
        if program is None:
            return TrafficLightColor.GREEN, 0
        cycle = sum(phase.duration_ms for phase in program.phases)
        offset = time_ms % cycle
        for phase in program.phases:
            if offset < phase.duration_ms:
                return phase.color, phase.duration_ms - offset
            offset -= phase.duration_ms
        return program.phases[-1].color, 0

    def _traffic_light_states(self, time_ms: int) -> list[TrafficLightState]:
        states = []
        for signal_id in sorted(self._programs):
            color, remaining = self._signal_state(signal_id, time_ms)
            states.append(
                TrafficLightState(
                    signal_id=signal_id,
                    simulation_time_ms=time_ms,
                    phase=color.value,
                    remaining_ms=remaining,
                )
            )
        return states

    def _vehicle_state(self, vehicle: _Vehicle) -> VehicleState:
        position, heading = self._position(self._lanes[vehicle.lane_id], vehicle.s_m)
        return VehicleState(
            experiment_id=self._experiment_id,
            vehicle_id=vehicle.demand.vehicle_id,
            simulation_time_ms=self._simulation_time_ms,
            sequence=self._sequence,
            automation_level=AutomationLevel.HUMAN,
            position=position,
            speed_mps=vehicle.speed_mps,
            acceleration_mps2=vehicle.acceleration_mps2,
            heading_rad=heading,
            lane_id=vehicle.lane_id,
            controller_id="native-traffic-engine",
            action=vehicle.action,
            risk_score=0.0,
            route_id=vehicle.demand.route_id,
        )

    @staticmethod
    def _position(lane: Lane, s_m: float) -> tuple[Vector3, float]:
        points = lane.centerline
        segment_lengths = [
            math.dist((left.x, left.y, left.z), (right.x, right.y, right.z))
            for left, right in zip(points, points[1:], strict=False)
        ]
        geometry_length = sum(segment_lengths)
        target = min(lane.length_m, s_m) / lane.length_m * geometry_length
        travelled = 0.0
        for left, right, length in zip(points, points[1:], segment_lengths, strict=False):
            if travelled + length >= target or length <= 1e-12:
                ratio = 0.0 if length <= 1e-12 else (target - travelled) / length
                return (
                    Vector3(
                        x=left.x + (right.x - left.x) * ratio,
                        y=left.y + (right.y - left.y) * ratio,
                        z=left.z + (right.z - left.z) * ratio,
                    ),
                    math.atan2(right.y - left.y, right.x - left.x),
                )
            travelled += length
        last, previous = points[-1], points[-2]
        return last, math.atan2(last.y - previous.y, last.x - previous.x)
