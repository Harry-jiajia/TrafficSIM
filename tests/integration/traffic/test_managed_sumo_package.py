from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import UUID

import pytest

from trafficverse.adapters.sumo import SumoTrafficEngineAdapter
from trafficverse.config.models import SumoConfig
from trafficverse.maps.sumo_package import load_sumo_package, stage_sumo_package

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
IMAGE2ROAD_CONFIG = REPOSITORY_ROOT / "configs/maps/image2road/image2road.sumocfg"

pytestmark = [pytest.mark.integration, pytest.mark.traffic]


@pytest.mark.skipif(
    os.getenv("TRAFFICVERSE_SUMO_PACKAGE_INTEGRATION") != "1" or shutil.which("sumo") is None,
    reason="set TRAFFICVERSE_SUMO_PACKAGE_INTEGRATION=1 with host SUMO available",
)
def test_image2road_managed_package_uses_host_sumo_and_cleans_up(tmp_path: Path) -> None:
    package = load_sumo_package(
        IMAGE2ROAD_CONFIG,
        allowed_root=REPOSITORY_ROOT / "configs/maps",
    )
    output_directory = tmp_path / "sumo"
    staged_config = stage_sumo_package(package, output_directory / "package")
    adapter = SumoTrafficEngineAdapter(UUID(int=1))
    try:
        adapter.load(
            SumoConfig(
                launch_mode="managed",
                config_file=str(staged_config),
                step_ms=package.step_ms,
                begin_time_ms=package.begin_time_ms,
                expected_version=None,
                output_directory=str(output_directory),
                connect_retries=30,
            )
        )

        snapshot = adapter.step(package.begin_time_ms + package.step_ms)

        assert snapshot.simulation_time_ms == 1000
        assert adapter.diagnostics().version is not None
        assert snapshot.vehicles
        assert snapshot.traffic_lights
        assert all(light.signal_id.startswith("sumo-tls:") for light in snapshot.traffic_lights)
    finally:
        adapter.close()

    assert not adapter.diagnostics().connected
