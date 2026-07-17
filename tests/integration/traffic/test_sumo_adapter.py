from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest

from trafficverse.adapters.sumo import SumoTrafficEngineAdapter
from trafficverse.config.models import SumoConfig

pytestmark = [pytest.mark.integration, pytest.mark.traffic]

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_external_sumo_produces_monotonic_town04_snapshots() -> None:
    if os.getenv("TRAFFICVERSE_SUMO_INTEGRATION") != "1":
        pytest.skip("set TRAFFICVERSE_SUMO_INTEGRATION=1 with SUMO listening on port 8813")
    config = SumoConfig(
        host=os.getenv("TRAFFICVERSE_SUMO_HOST", "127.0.0.1"),
        port=int(os.getenv("TRAFFICVERSE_SUMO_PORT", "8813")),
        config_file=str(REPOSITORY_ROOT / "configs/maps/town04/map.sumocfg"),
        expected_version="1.27.1",
    )
    adapter = SumoTrafficEngineAdapter(UUID(int=42))
    observed_vehicle_ids: set[str] = set()
    try:
        adapter.load(config)
        for sequence in range(1, 501):
            snapshot = adapter.step(sequence * config.step_ms)
            assert snapshot.sequence == sequence
            assert snapshot.simulation_time_ms == sequence * config.step_ms
            assert all(
                vehicle.simulation_time_ms == snapshot.simulation_time_ms
                for vehicle in snapshot.vehicles
            )
            observed_vehicle_ids.update(vehicle.vehicle_id for vehicle in snapshot.vehicles)
        assert len(observed_vehicle_ids) == 50
        assert adapter.diagnostics().sequence == 500
    finally:
        adapter.close()
