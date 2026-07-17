import hashlib
from pathlib import Path

import pytest
import yaml

from trafficverse.config.loader import (
    configuration_hash,
    load_scenario,
    validate_map_manifest,
    validate_scenario_environment,
)
from trafficverse.domain.enums import ErrorCode
from trafficverse.domain.errors import ConfigurationError

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_PATH = REPOSITORY_ROOT / "configs" / "scenarios" / "core-run-town04.yaml"


def test_core_run_scenario_loads_structurally() -> None:
    scenario = load_scenario(SCENARIO_PATH, apply_environment=False)
    assert scenario.scenario.name == "core-run-town04"
    assert scenario.traffic.vehicles == 50
    assert scenario.sumo.host == "127.0.0.1"
    assert scenario.sumo.port == 8813
    assert sum(scenario.automation.proportions.values()) == 1.0


def test_configuration_hash_is_stable() -> None:
    first = load_scenario(SCENARIO_PATH, apply_environment=False)
    second = load_scenario(SCENARIO_PATH, apply_environment=False)
    assert configuration_hash(first) == configuration_hash(second)


def test_scenario_rejects_divergent_sumo_step(tmp_path: Path) -> None:
    payload = yaml.safe_load(SCENARIO_PATH.read_text(encoding="utf-8"))
    payload["sumo"]["step_ms"] = 100
    invalid_path = tmp_path / "invalid.yaml"
    invalid_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ConfigurationError) as captured:
        load_scenario(invalid_path, apply_environment=False)
    assert "simulation step values must match" in captured.value.details["reason"]


def test_invalid_automation_proportions_report_field(tmp_path: Path) -> None:
    payload = yaml.safe_load(SCENARIO_PATH.read_text(encoding="utf-8"))
    payload["automation"]["proportions"]["HUMAN"] = 0.5
    invalid_path = tmp_path / "invalid.yaml"
    invalid_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ConfigurationError) as captured:
        load_scenario(invalid_path, apply_environment=False)

    assert captured.value.code is ErrorCode.SCENARIO_VALIDATION_FAILED
    assert "automation.proportions" in captured.value.details["reason"]


@pytest.mark.parametrize(
    ("section", "field", "value", "expected_location"),
    [
        ("roi", "radius_m", -1.0, "roi.radius_m"),
        ("simulation", "step_ms", 0, "simulation.step_ms"),
        ("simulation", "duration_ms", 101, "simulation"),
    ],
)
def test_invalid_runtime_values_report_field(
    tmp_path: Path,
    section: str,
    field: str,
    value: object,
    expected_location: str,
) -> None:
    payload = yaml.safe_load(SCENARIO_PATH.read_text(encoding="utf-8"))
    payload[section][field] = value
    invalid_path = tmp_path / "invalid.yaml"
    invalid_path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ConfigurationError) as captured:
        load_scenario(invalid_path, apply_environment=False)

    assert expected_location in captured.value.details["reason"]


def test_invalid_carla_port_environment_override_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRAFFICVERSE_CARLA_PORT", "70000")

    with pytest.raises(ConfigurationError) as captured:
        load_scenario(SCENARIO_PATH)

    assert captured.value.code is ErrorCode.SCENARIO_VALIDATION_FAILED
    assert "port" in captured.value.details["reason"]


def test_local_simulator_environment_overrides_are_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRAFFICVERSE_CARLA_HOST", "10.0.0.8")
    monkeypatch.setenv("TRAFFICVERSE_CARLA_PORT", "2200")
    monkeypatch.setenv("TRAFFICVERSE_CARLA_TIMEOUT_S", "45.5")
    monkeypatch.setenv("TRAFFICVERSE_SUMO_HOST", "10.0.0.9")
    monkeypatch.setenv("TRAFFICVERSE_SUMO_PORT", "9913")

    scenario = load_scenario(SCENARIO_PATH)

    assert scenario.carla.host == "10.0.0.8"
    assert scenario.carla.port == 2200
    assert scenario.carla.timeout_s == 45.5
    assert scenario.sumo.host == "10.0.0.9"
    assert scenario.sumo.port == 9913


def test_invalid_carla_timeout_environment_override_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRAFFICVERSE_CARLA_TIMEOUT_S", "slow")

    with pytest.raises(ConfigurationError) as captured:
        load_scenario(SCENARIO_PATH)

    assert captured.value.code is ErrorCode.SCENARIO_VALIDATION_FAILED
    assert captured.value.details["variable"] == "TRAFFICVERSE_CARLA_TIMEOUT_S"


def test_environment_validation_reports_missing_assets(tmp_path: Path) -> None:
    scenario = load_scenario(SCENARIO_PATH, apply_environment=False)
    with pytest.raises(ConfigurationError) as captured:
        validate_scenario_environment(scenario, repository_root=tmp_path)

    assert captured.value.code is ErrorCode.CONFIGURATION_NOT_FOUND
    assert set(captured.value.details) == {
        "traffic.network",
        "traffic.routes",
        "traffic.signals",
        "map_registration.manifest",
        "sumo.config_file",
    }


def _write_manifest(
    directory: Path,
    *,
    validated: bool = True,
    checksum: str | None = None,
    carla_version: str = "0.9.16",
) -> Path:
    asset = directory / "Town04.xodr"
    asset.write_text("town04", encoding="utf-8")
    digest = checksum or f"sha256:{hashlib.sha256(asset.read_bytes()).hexdigest()}"
    manifest = {
        "schema_version": "1.1",
        "map_id": "town04-carla-0.9.16-sumo-1.27.1-v1",
        "carla_map": "Town04",
        "carla_version": carla_version,
        "sumo_version": "1.27.1",
        "network_schema_version": "traffic-network/1.0",
        "compiler_version": "1.0.0",
        "source_repository": "https://github.com/carla-simulator/carla",
        "source_ref": "test-ref",
        "sumo_generation_command": "python scripts/maps/generate_town04_sumo.py",
        "validated": validated,
        "max_registration_error_m": 0.5,
        "strict_signal_mapping": True,
        "files": {"Town04.xodr": digest},
    }
    path = directory / "manifest.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return path


def test_valid_map_manifest_passes_checksum_and_version_checks(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path)
    manifest = validate_map_manifest(
        manifest_path,
        expected_carla_version="0.9.16",
        expected_network_schema_version="traffic-network/1.0",
    )
    assert manifest.validated


@pytest.mark.parametrize(
    ("validated", "checksum", "carla_version", "expected_code"),
    [
        (False, None, "0.9.16", ErrorCode.MAP_ASSET_INVALID),
        (True, f"sha256:{'0' * 64}", "0.9.16", ErrorCode.MAP_ASSET_INVALID),
        (True, None, "0.9.15", ErrorCode.VERSION_MISMATCH),
    ],
)
def test_invalid_map_manifest_fails_readiness(
    tmp_path: Path,
    validated: bool,
    checksum: str | None,
    carla_version: str,
    expected_code: ErrorCode,
) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        validated=validated,
        checksum=checksum,
        carla_version=carla_version,
    )
    with pytest.raises(ConfigurationError) as captured:
        validate_map_manifest(
            manifest_path,
            expected_carla_version="0.9.16",
            expected_network_schema_version="traffic-network/1.0",
        )
    assert captured.value.code is expected_code
