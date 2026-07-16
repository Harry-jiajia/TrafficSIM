import json
from pathlib import Path

import yaml
from pydantic import BaseModel

from trafficverse.api.contracts import build_openapi_contract
from trafficverse.api.models import ClientCommand
from trafficverse.config.models import RuntimeBaseline, ScenarioConfig
from trafficverse.domain.models import VehicleState, WebSocketEnvelope
from trafficverse.maps.models import RoadNetwork

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXPECTED: dict[Path, type[BaseModel]] = {
    Path("contracts/runtime_baseline.schema.json"): RuntimeBaseline,
    Path("contracts/scenario.schema.json"): ScenarioConfig,
    Path("contracts/traffic_network.schema.json"): RoadNetwork,
    Path("contracts/websocket/vehicle_state.schema.json"): VehicleState,
    Path("contracts/websocket/websocket_envelope.schema.json"): WebSocketEnvelope,
    Path("contracts/websocket/client_command.schema.json"): ClientCommand,
}


def test_generated_json_schemas_match_models() -> None:
    mismatches: list[str] = []
    for relative_path, model in EXPECTED.items():
        path = REPOSITORY_ROOT / relative_path
        if not path.is_file():
            mismatches.append(f"missing {relative_path}")
            continue
        actual = json.loads(path.read_text(encoding="utf-8"))
        if actual != model.model_json_schema():
            mismatches.append(f"stale {relative_path}")
    assert mismatches == []


def test_generated_openapi_matches_routes() -> None:
    path = REPOSITORY_ROOT / "contracts/openapi.yaml"
    assert path.is_file()
    actual = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert actual == build_openapi_contract()
