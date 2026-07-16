import json
from pathlib import Path
from uuid import UUID

import yaml

from trafficverse.config.models import TrafficEngineConfig
from trafficverse.domain.enums import LaneChangeDirection
from trafficverse.domain.models import ControlCommand, Vector3
from trafficverse.maps import load_network
from trafficverse.maps.models import Lane, LaneLink, RoadNetwork, TrafficSignal
from trafficverse.traffic import NativeTrafficEngine
from trafficverse.traffic.routing import shortest_path


def _lane(
    lane_id: str,
    y: float,
    *,
    successor: str,
    left: str | None = None,
    right: str | None = None,
) -> Lane:
    return Lane(
        lane_id=lane_id,
        road_id=lane_id,
        section_index=0,
        source_lane_id=-1,
        length_m=100,
        width_m=3.5,
        speed_limit_mps=12,
        centerline=(Vector3(x=0, y=y), Vector3(x=100, y=y)),
        successor_ids=(successor,),
        left_lane_id=left,
        right_lane_id=right,
    )


def _assets(
    tmp_path: Path, *, reverse_lanes: bool = False, reverse_routes: bool = False
) -> TrafficEngineConfig:
    tmp_path.mkdir(parents=True, exist_ok=True)
    lanes = [
        _lane("a", 0, successor="a2", right="b"),
        _lane("b", -3.5, successor="b2", left="a"),
        Lane(
            lane_id="a2",
            road_id="a2",
            section_index=0,
            source_lane_id=-1,
            length_m=100,
            width_m=3.5,
            speed_limit_mps=12,
            centerline=(Vector3(x=100, y=0), Vector3(x=200, y=0)),
            predecessor_ids=("a",),
        ),
        Lane(
            lane_id="b2",
            road_id="b2",
            section_index=0,
            source_lane_id=-1,
            length_m=100,
            width_m=3.5,
            speed_limit_mps=12,
            centerline=(Vector3(x=100, y=-3.5), Vector3(x=200, y=-3.5)),
            predecessor_ids=("b",),
        ),
    ]
    if reverse_lanes:
        lanes.reverse()
    network = RoadNetwork(
        map_id="engine-test",
        lanes=tuple(lanes),
        links=(
            LaneLink(
                link_id="a-a2",
                from_lane_id="a",
                to_lane_id="a2",
                signal_id="signal-1",
                stop_line_s_m=100,
            ),
            LaneLink(link_id="b-b2", from_lane_id="b", to_lane_id="b2"),
        ),
        signals=(
            TrafficSignal(
                signal_id="signal-1",
                opendrive_id="1",
                road_id="a",
                controlled_link_ids=("a-a2",),
            ),
        ),
    )
    network_path = tmp_path / "network.json"
    network_path.write_text(json.dumps(network.model_dump(mode="json")), encoding="utf-8")
    routes_path = tmp_path / "routes.yaml"
    routes = [
        {
            "route_id": "route-1",
            "lane_ids": ["a", "a2"],
            "vehicle_id": "vehicle-1",
            "depart_ms": 0,
            "desired_speed_mps": 10,
        },
        {
            "route_id": "route-2",
            "lane_ids": ["a", "a2"],
            "vehicle_id": "vehicle-2",
            "depart_ms": 1000,
            "desired_speed_mps": 10,
        },
    ]
    if reverse_routes:
        routes.reverse()
    routes_path.write_text(
        yaml.safe_dump({"schema_version": "1.0", "routes": routes}), encoding="utf-8"
    )
    signals_path = tmp_path / "signals.yaml"
    signals_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "programs": [
                    {
                        "signal_id": "signal-1",
                        "phases": [{"color": "RED", "duration_ms": 120000}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return TrafficEngineConfig(
        network_path=str(network_path),
        routes_path=str(routes_path),
        signals_path=str(signals_path),
    )


def test_fixed_step_following_and_red_light_stop_without_collision(tmp_path: Path) -> None:
    engine = NativeTrafficEngine(UUID(int=1))
    engine.load(_assets(tmp_path))
    snapshot = None
    for tick in range(1, 401):
        snapshot = engine.step(tick * 50)

    assert snapshot is not None
    assert snapshot.traffic_lights[0].phase == "RED"
    positions = sorted(vehicle.position.x for vehicle in snapshot.vehicles)
    assert positions[-1] <= 97.5 + 1e-6
    assert positions[-1] - positions[0] >= 7.0 - 1e-6
    assert all(vehicle.speed_mps >= 0 for vehicle in snapshot.vehicles)


def test_batch_control_rejects_one_vehicle_without_blocking_safe_lane_change(
    tmp_path: Path,
) -> None:
    engine = NativeTrafficEngine(UUID(int=2))
    engine.load(_assets(tmp_path))
    engine.step(50)
    engine.apply_controls(
        {
            "missing": ControlCommand(stop_requested=True),
            "vehicle-1": ControlCommand(lane_change=LaneChangeDirection.RIGHT),
        }
    )
    snapshot = engine.step(100)

    assert (
        next(vehicle for vehicle in snapshot.vehicles if vehicle.vehicle_id == "vehicle-1").lane_id
        == "b"
    )
    assert engine.diagnostics().completed_lane_changes == 1
    assert engine.diagnostics().rejected_controls == 1


def test_delayed_spawn_green_restart_and_arrival_exit(tmp_path: Path) -> None:
    config = _assets(tmp_path)
    Path(config.signals_path).write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "programs": [
                    {
                        "signal_id": "signal-1",
                        "phases": [
                            {"color": "RED", "duration_ms": 20000},
                            {"color": "GREEN", "duration_ms": 120000},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    engine = NativeTrafficEngine(UUID(int=4))
    engine.load(config)
    snapshots = [engine.step(tick * 50) for tick in range(1, 400)]

    assert "vehicle-2" not in {vehicle.vehicle_id for vehicle in snapshots[19].vehicles}
    assert "vehicle-2" in {vehicle.vehicle_id for vehicle in snapshots[-1].vehicles}
    lead = next(vehicle for vehicle in snapshots[-1].vehicles if vehicle.vehicle_id == "vehicle-1")
    assert lead.speed_mps < 0.01
    assert lead.action.value == "STOP"
    assert lead.position.x <= 97.5 + 1e-6

    for tick in range(400, 801):
        snapshot = engine.step(tick * 50)

    assert engine.diagnostics().arrived_vehicles >= 1
    assert all(vehicle.position.x > 97.5 for vehicle in snapshot.vehicles)


def test_seed_and_input_iteration_order_produce_identical_snapshots(tmp_path: Path) -> None:
    first = NativeTrafficEngine(UUID(int=3))
    second = NativeTrafficEngine(UUID(int=3))
    first.load(_assets(tmp_path / "first"))
    second.load(_assets(tmp_path / "second", reverse_lanes=True, reverse_routes=True))

    first_payloads = []
    second_payloads = []
    for tick in range(1, 101):
        if tick == 50:
            first.apply_controls(
                {
                    "vehicle-2": ControlCommand(desired_speed_mps=8),
                    "vehicle-1": ControlCommand(desired_speed_mps=9),
                }
            )
            second.apply_controls(
                {
                    "vehicle-1": ControlCommand(desired_speed_mps=9),
                    "vehicle-2": ControlCommand(desired_speed_mps=8),
                }
            )
        first_payloads.append(first.step(tick * 50).model_dump_json())
        second_payloads.append(second.step(tick * 50).model_dump_json())

    assert first_payloads == second_payloads


def test_dijkstra_returns_reachable_length_weighted_route(tmp_path: Path) -> None:
    config = _assets(tmp_path)
    network = load_network(Path(config.network_path))
    assert shortest_path(network, "a", "a2") == ("a", "a2")
