from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
from tests.fakes import FakeDataLogger, FakeExperimentRepository

from trafficverse.adapters.carla import CarlaAdapter
from trafficverse.application.simulation_manager import SimulationManager
from trafficverse.config.loader import load_scenario
from trafficverse.domain.enums import ExperimentStatus
from trafficverse.maps.validation import load_network
from trafficverse.roi import (
    CoordinateTransformer,
    RoiDefinition,
    RoiSynchronizer,
    SignalSynchronizer,
)
from trafficverse.traffic import NativeTrafficEngine

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_PATH = REPOSITORY_ROOT / "configs/scenarios/core-run-town04.yaml"
MAP_DIRECTORY = REPOSITORY_ROOT / "configs/maps/town04"


@pytest.mark.integration
@pytest.mark.carla
def test_remote_town04_native_roi_core_run() -> None:
    if os.getenv("TRAFFICVERSE_CARLA_INTEGRATION") != "1":
        pytest.skip("set TRAFFICVERSE_CARLA_INTEGRATION=1 on the remote Linux runtime")

    async def exercise() -> None:
        experiment_id = uuid4()
        scenario = load_scenario(SCENARIO_PATH, apply_environment=True)
        path_updates = {
            field: str(REPOSITORY_ROOT / str(getattr(scenario.traffic_engine, field)))
            for field in ("network_path", "routes_path", "signals_path")
        }
        scenario = scenario.model_copy(
            update={"traffic_engine": scenario.traffic_engine.model_copy(update=path_updates)}
        )
        transformer = CoordinateTransformer.from_yaml(
            MAP_DIRECTORY / "registration.yaml",
            max_error_m=0.001,
        )
        focus = scenario.roi.focus
        assert focus.x is not None and focus.y is not None
        roi = RoiSynchronizer(
            RoiDefinition(
                radius_m=scenario.roi.radius_m,
                buffer_m=scenario.roi.buffer_m,
                max_actors=scenario.roi.max_actors,
                focus_x=focus.x,
                focus_y=focus.y,
            ),
            transformer,
        )
        signals = SignalSynchronizer.from_assets(
            MAP_DIRECTORY / "network.json",
            MAP_DIRECTORY / "signals.yaml",
        )
        traffic = NativeTrafficEngine(experiment_id)
        carla = CarlaAdapter()
        repository = FakeExperimentRepository()
        repository.statuses[experiment_id] = ExperimentStatus.CREATED
        manager = SimulationManager(
            scenario=scenario,
            carla_map_name="Town04",
            traffic=traffic,
            carla=carla,
            experiments=repository,
            data_logger=FakeDataLogger(),
            roi_planner=roi,
            signal_planner=signals,
        )

        await manager.prepare(experiment_id)
        await manager.start()
        maximum_bindings = 0
        seen_vehicle_ids: set[str] = set()
        previous_lanes: dict[str, str] = {}
        network = load_network(MAP_DIRECTORY / "network.json")
        controlled_transitions = {
            (link.from_lane_id, link.to_lane_id)
            for link in network.links
            if link.signal_id is not None
        }
        crossed_controlled_signal = False
        for _ in range(500):
            frame = await manager.run_tick()
            maximum_bindings = max(maximum_bindings, len(roi.bindings))
            for vehicle in frame.traffic.vehicles:
                seen_vehicle_ids.add(vehicle.vehicle_id)
                previous = previous_lanes.get(vehicle.vehicle_id)
                if previous is not None and (previous, vehicle.lane_id) in controlled_transitions:
                    crossed_controlled_signal = True
                previous_lanes[vehicle.vehicle_id] = vehicle.lane_id

        await manager.stop("REMOTE_ROI_CORE_RUN_COMPLETE")

        assert len(seen_vehicle_ids) == 50
        assert maximum_bindings >= 10
        assert crossed_controlled_signal
        assert transformer.maximum_control_point_error_m <= 0.5
        assert repository.statuses[experiment_id] is ExperimentStatus.COMPLETED
        assert carla.diagnostics().owned_actor_count == 0

    asyncio.run(exercise())
