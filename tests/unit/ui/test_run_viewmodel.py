from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from ui.models import ExperimentStatus
from ui.viewmodels import RunViewModel

EXPERIMENT_ID = UUID("00000000-0000-0000-0000-000000000010")
SCENARIO_ID = UUID("00000000-0000-0000-0000-000000000042")


class FakeRest(QObject):
    request_succeeded = Signal(str, object)
    request_failed = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, object]] = []

    def check_readiness(self) -> None:
        self.calls.append(("ready", None))

    def check_health(self) -> None:
        self.calls.append(("health", None))

    def list_maps(self) -> None:
        self.calls.append(("maps", None))

    def get_map_network(self, map_id: str) -> None:
        self.calls.append(("network", map_id))

    def get_asset_map_network(self, map_id: str) -> None:
        self.calls.append(("asset-network", map_id))

    def get_map_manifest(self, map_id: str) -> None:
        self.calls.append(("manifest", map_id))

    def get_import_job(self, job_id: UUID) -> None:
        self.calls.append(("import-job", job_id))

    def import_map(self, path: Path) -> None:
        self.calls.append(("import", path))

    def create_experiment(self, scenario_id: UUID, map_id: str) -> None:
        self.calls.append(("create", (scenario_id, map_id)))


class FakeRealtime(QObject):
    connection_changed = Signal(str)
    envelope_received = Signal(object)
    protocol_error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.connected: UUID | None = None
        self.sent: list[tuple[str, dict[str, object]]] = []
        self.snapshot_requests = 0

    def connect_to_experiment(self, experiment_id: UUID) -> None:
        self.connected = experiment_id

    def send_command(self, command: str, payload: dict[str, object]) -> str:
        self.sent.append((command, payload))
        return "message-1"

    def request_snapshot(self) -> str:
        self.snapshot_requests += 1
        return "snapshot-1"


def _app() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


def _viewmodel() -> tuple[RunViewModel, FakeRest, FakeRealtime]:
    _app()
    rest = FakeRest()
    realtime = FakeRealtime()
    viewmodel = RunViewModel(rest, realtime, SCENARIO_ID)  # type: ignore[arg-type]
    return viewmodel, rest, realtime


def _envelope(message_type: str, sequence: int, payload: object) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "type": message_type,
        "message_id": f"message-{sequence}",
        "correlation_id": None,
        "experiment_id": str(EXPERIMENT_ID),
        "simulation_time_ms": sequence * 50,
        "sequence": sequence,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


def _vehicle(sequence: int) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "experiment_id": str(EXPERIMENT_ID),
        "vehicle_id": "vehicle-1",
        "simulation_time_ms": sequence * 50,
        "sequence": sequence,
        "automation_level": "HUMAN",
        "position": {"x": 1.0, "y": 2.0, "z": 0.0},
        "speed_mps": 5.0,
        "acceleration_mps2": 0.0,
        "heading_rad": 0.0,
        "lane_id": "lane-1",
        "target_lane_id": None,
        "controller_id": "fixture",
        "action": "KEEP_LANE",
        "risk_score": 0.0,
        "route_id": "route-1",
    }


def test_initialize_checks_api_health_without_requesting_experiment_readiness() -> None:
    viewmodel, rest, _ = _viewmodel()
    connection_states: list[str] = []
    viewmodel.connection_changed.connect(connection_states.append)

    viewmodel.initialize()
    viewmodel.handle_rest_success(
        "health",
        {"status": "ok", "service": "trafficverse-api"},
    )

    assert rest.calls == [("health", None), ("maps", None)]
    assert connection_states == ["API_CONNECTED"]


def test_map_catalog_skips_core_run_asset_and_auto_selects_sumo_package() -> None:
    viewmodel, rest, _ = _viewmodel()
    notifications: list[tuple[str, str]] = []
    viewmodel.notification.connect(lambda level, message: notifications.append((level, message)))
    viewmodel.handle_rest_success(
        "maps.list",
        [
            {
                "map_id": "town04",
                "carla_map": "Town04",
                "carla_version": "0.9.16",
                "validated": True,
                "network_schema_version": "traffic-network/1.0",
            },
            {
                "map_id": "image2road",
                "kind": "sumo",
                "display_name": "图像识别路网",
                "carla_map": None,
                "carla_version": None,
                "validated": True,
                "network_schema_version": "sumo-net/display-1.0",
                "manifest_available": False,
                "sumo_config_file": "image2road.sumocfg",
                "sumo_step_ms": 1000,
            },
        ],
    )
    viewmodel.select_map("town04")
    viewmodel.create_experiment()

    assert ("manifest", "town04") in rest.calls
    assert ("network", "town04") not in rest.calls
    assert ("network", "image2road") in rest.calls
    assert ("create", (SCENARIO_ID, "image2road")) in rest.calls
    assert notifications[-1] == ("error", "所选资产不是可直接运行的 SUMO 场景包。")


def test_native_sumo_package_loads_network_without_town04_manifest() -> None:
    viewmodel, rest, _ = _viewmodel()
    viewmodel.handle_rest_success(
        "maps.list",
        [
            {
                "map_id": "image2road",
                "kind": "sumo",
                "display_name": "图像识别路网",
                "carla_map": None,
                "carla_version": None,
                "validated": True,
                "network_schema_version": "sumo-net/display-1.0",
                "manifest_available": False,
                "sumo_config_file": "image2road.sumocfg",
                "sumo_step_ms": 1000,
            }
        ],
    )
    viewmodel.create_experiment()

    assert ("network", "image2road") in rest.calls
    assert ("manifest", "image2road") not in rest.calls
    assert ("create", (SCENARIO_ID, "image2road")) in rest.calls


def test_asset_manifest_and_preview_network_are_forwarded_separately() -> None:
    viewmodel, rest, _ = _viewmodel()
    manifests: list[tuple[str, object]] = []
    previews: list[tuple[str, object]] = []
    viewmodel.map_manifest_changed.connect(
        lambda map_id, manifest: manifests.append((map_id, manifest))
    )
    viewmodel.asset_network_changed.connect(
        lambda map_id, network: previews.append((map_id, network))
    )
    viewmodel.handle_rest_success(
        "maps.list",
        [
            {
                "map_id": "town04",
                "carla_map": "Town04",
                "carla_version": "0.9.16",
                "validated": True,
                "network_schema_version": "traffic-network/1.0",
            }
        ],
    )
    manifest = {
        "schema_version": "1.1",
        "map_id": "town04",
        "carla_map": "Town04",
        "carla_version": "0.9.16",
        "sumo_version": "1.27.1",
        "network_schema_version": "traffic-network/1.0",
        "compiler_version": "1.1.0",
        "source_repository": "https://example.invalid/maps",
        "source_ref": "fixture",
        "sumo_generation_command": "fixture",
        "validated": True,
        "max_registration_error_m": 0.001,
        "strict_signal_mapping": True,
        "files": {"network.geojson": "sha256:" + "a" * 64},
    }
    viewmodel.handle_rest_success("map.manifest:town04", manifest)
    viewmodel.preview_map_asset("town04")
    network = {"type": "FeatureCollection", "features": []}
    viewmodel.handle_rest_success("asset.map.network:town04", network)

    assert manifests and manifests[0][0] == "town04"
    assert ("asset-network", "town04") in rest.calls
    assert previews == [("town04", network)]


def test_start_prepares_created_experiment_then_starts_when_ready() -> None:
    viewmodel, _, realtime = _viewmodel()
    viewmodel.handle_rest_success(
        "experiment.create",
        {
            "experiment_id": str(EXPERIMENT_ID),
            "status": "CREATED",
            "simulation_time_ms": 0,
            "speed_multiplier": 1.0,
        },
    )
    viewmodel.start()
    viewmodel.handle_envelope(_envelope("experiment.state.changed", 0, {"status": "READY"}))

    assert realtime.connected == EXPERIMENT_ID
    assert realtime.sent == [
        ("experiment.prepare", {}),
        ("experiment.start", {}),
    ]
    assert viewmodel.status is ExperimentStatus.READY


def test_vehicle_sequence_gap_requests_world_snapshot() -> None:
    viewmodel, _, realtime = _viewmodel()
    viewmodel.handle_rest_success(
        "experiment.create",
        {
            "experiment_id": str(EXPERIMENT_ID),
            "status": "RUNNING",
            "simulation_time_ms": 0,
            "speed_multiplier": 1.0,
        },
    )
    viewmodel.handle_envelope(
        _envelope(
            "world.snapshot",
            2,
            {
                "traffic": {"vehicles": [_vehicle(2)], "traffic_lights": []},
                "carla": None,
                "events": [],
                "metrics": [],
            },
        )
    )
    viewmodel.handle_envelope(_envelope("vehicle.delta", 4, {"vehicles": [_vehicle(4)]}))

    assert realtime.snapshot_requests == 1


def test_running_world_deltas_forward_new_vehicle_positions_to_the_map() -> None:
    viewmodel, _, _ = _viewmodel()
    viewmodel.handle_rest_success(
        "experiment.create",
        {
            "experiment_id": str(EXPERIMENT_ID),
            "status": "RUNNING",
            "simulation_time_ms": 0,
            "speed_multiplier": 1.0,
        },
    )
    positions: list[tuple[float, float]] = []
    viewmodel.vehicles_changed.connect(
        lambda vehicles: positions.append((vehicles[0].position.x, vehicles[0].position.y))
    )
    first = _vehicle(1)
    second = _vehicle(2)
    second["position"] = {"x": 8.0, "y": 5.0, "z": 0.0}

    viewmodel.handle_envelope(_envelope("vehicle.delta", 1, {"vehicles": [first]}))
    viewmodel.handle_envelope(_envelope("vehicle.delta", 2, {"vehicles": [second]}))

    assert positions == [(1.0, 2.0), (8.0, 5.0)]
