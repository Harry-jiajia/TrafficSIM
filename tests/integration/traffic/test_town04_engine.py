import hashlib
from pathlib import Path
from uuid import UUID

import pytest

from trafficverse.config.loader import load_scenario
from trafficverse.domain.enums import LaneChangeDirection
from trafficverse.domain.models import ControlCommand
from trafficverse.maps import OpenDriveMapCompiler, load_network
from trafficverse.traffic import NativeTrafficEngine

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.traffic
def test_town04_compiler_is_byte_deterministic(tmp_path: Path) -> None:
    source = ROOT / "configs/maps/town04/Town04.xodr"
    first = tmp_path / "first"
    second = tmp_path / "second"
    OpenDriveMapCompiler().compile(source, first, map_id="town04-carla-0.9.16-native-1.0")
    OpenDriveMapCompiler().compile(source, second, map_id="town04-carla-0.9.16-native-1.0")

    for name in ("network.json", "network.geojson", "routes.yaml", "signals.yaml"):
        assert (
            hashlib.sha256((first / name).read_bytes()).digest()
            == hashlib.sha256((second / name).read_bytes()).digest()
        )


@pytest.mark.traffic
def test_town04_fifty_vehicle_two_minute_native_smoke() -> None:
    scenario = load_scenario(
        ROOT / "configs/scenarios/core-run-town04.yaml", apply_environment=False
    )
    config = scenario.traffic_engine.model_copy(
        update={
            "network_path": str(ROOT / scenario.traffic_engine.network_path),
            "routes_path": str(ROOT / scenario.traffic_engine.routes_path),
            "signals_path": str(ROOT / scenario.traffic_engine.signals_path),
        }
    )
    network = load_network(Path(config.network_path))
    lanes = {lane.lane_id: lane for lane in network.lanes}
    engine = NativeTrafficEngine(UUID(int=scenario.scenario.seed))
    replay = NativeTrafficEngine(UUID(int=scenario.scenario.seed))
    engine.load(config)
    replay.load(config)
    seen: set[str] = set()
    requested = False
    previous_lanes: dict[str, str] = {}
    controlled_transitions = {
        (link.from_lane_id, link.to_lane_id) for link in network.links if link.signal_id is not None
    }
    crossed_signal = False
    for tick in range(1, 2401):
        snapshot = engine.step(tick * 50)
        replay_snapshot = replay.step(tick * 50)
        assert (
            hashlib.sha256(snapshot.model_dump_json().encode()).digest()
            == hashlib.sha256(replay_snapshot.model_dump_json().encode()).digest()
        )
        seen.update(vehicle.vehicle_id for vehicle in snapshot.vehicles)
        for vehicle in snapshot.vehicles:
            previous = previous_lanes.get(vehicle.vehicle_id)
            if previous is not None and (previous, vehicle.lane_id) in controlled_transitions:
                crossed_signal = True
            previous_lanes[vehicle.vehicle_id] = vehicle.lane_id
        if not requested:
            candidate = next(
                (
                    vehicle
                    for vehicle in snapshot.vehicles
                    if lanes[vehicle.lane_id].left_lane_id is not None
                    or lanes[vehicle.lane_id].right_lane_id is not None
                ),
                None,
            )
            if candidate is not None:
                direction = (
                    LaneChangeDirection.LEFT
                    if lanes[candidate.lane_id].left_lane_id is not None
                    else LaneChangeDirection.RIGHT
                )
                command = {candidate.vehicle_id: ControlCommand(lane_change=direction)}
                engine.apply_controls(command)
                replay.apply_controls(command)
                requested = True

    diagnostics = engine.diagnostics()
    assert len(seen) == 50
    assert len(snapshot.traffic_lights) > 0
    assert crossed_signal
    assert diagnostics.completed_lane_changes >= 1
    assert diagnostics.p95_step_duration_ms < 50.0
