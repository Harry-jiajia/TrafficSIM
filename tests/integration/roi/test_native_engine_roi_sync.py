from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from tests.fakes import FakeCarlaPort, FakeDataLogger, FakeExperimentRepository

from trafficverse.application.simulation_manager import SimulationManager
from trafficverse.config.loader import load_scenario
from trafficverse.domain.enums import ExperimentStatus
from trafficverse.domain.models import CarlaTrafficLight
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
@pytest.mark.traffic
def test_native_engine_roi_and_signal_sync_close_without_orphan_actors() -> None:
    async def exercise() -> None:
        experiment_id = uuid4()
        scenario = load_scenario(SCENARIO_PATH, apply_environment=False)
        path_updates = {
            field: str(REPOSITORY_ROOT / str(getattr(scenario.traffic_engine, field)))
            for field in ("network_path", "routes_path", "signals_path")
        }
        scenario = scenario.model_copy(
            update={"traffic_engine": scenario.traffic_engine.model_copy(update=path_updates)}
        )
        network = load_network(MAP_DIRECTORY / "network.json")
        runtime_lights = tuple(
            CarlaTrafficLight(
                actor_id=10_000 + index,
                opendrive_id=signal.opendrive_id,
                frozen=True,
            )
            for index, signal in enumerate(network.signals)
        )
        transformer = CoordinateTransformer.from_yaml(
            MAP_DIRECTORY / "registration.yaml",
            max_error_m=0.001,
        )
        roi = RoiSynchronizer(
            RoiDefinition(
                radius_m=10_000.0,
                buffer_m=100.0,
                max_actors=10,
                focus_x=0.0,
                focus_y=0.0,
            ),
            transformer,
        )
        signals = SignalSynchronizer.from_assets(
            MAP_DIRECTORY / "network.json",
            MAP_DIRECTORY / "signals.yaml",
        )
        traffic = NativeTrafficEngine(experiment_id)
        carla = FakeCarlaPort(runtime_lights)
        repository = FakeExperimentRepository()
        repository.statuses[experiment_id] = ExperimentStatus.CREATED
        logger = FakeDataLogger()
        manager = SimulationManager(
            scenario=scenario,
            carla_map_name="Town04",
            traffic=traffic,
            carla=carla,
            experiments=repository,
            data_logger=logger,
            roi_planner=roi,
            signal_planner=signals,
        )

        await manager.prepare(experiment_id)
        await manager.start()
        for _ in range(500):
            await manager.run_tick()
        maximum_actor_count = max(
            frame.carla.actor_count for frame in logger.frames if frame.carla is not None
        )
        seen_vehicle_ids = {
            vehicle.vehicle_id for frame in logger.frames for vehicle in frame.traffic.vehicles
        }
        controlled_transitions = {
            (link.from_lane_id, link.to_lane_id)
            for link in network.links
            if link.signal_id is not None
        }
        previous_lanes: dict[str, str] = {}
        crossed_controlled_signal = False
        for frame in logger.frames:
            for vehicle in frame.traffic.vehicles:
                previous = previous_lanes.get(vehicle.vehicle_id)
                if previous is not None and (previous, vehicle.lane_id) in controlled_transitions:
                    crossed_controlled_signal = True
                previous_lanes[vehicle.vehicle_id] = vehicle.lane_id
        assert maximum_actor_count == 10
        assert len(seen_vehicle_ids) == 50
        assert crossed_controlled_signal
        assert len(roi.bindings) <= 10
        assert carla.traffic_light_updates

        await manager.stop("ROI_INTEGRATION_COMPLETE")

        assert repository.statuses[experiment_id] is ExperimentStatus.COMPLETED
        assert carla.actor_ids == set()

    asyncio.run(exercise())
