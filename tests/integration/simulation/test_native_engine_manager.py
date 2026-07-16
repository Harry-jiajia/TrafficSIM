import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from tests.fakes import FakeCarlaPort, FakeDataLogger, FakeExperimentRepository

from trafficverse.application.simulation_manager import SimulationManager
from trafficverse.config.loader import load_scenario
from trafficverse.domain.enums import ExperimentStatus
from trafficverse.traffic import NativeTrafficEngine

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_PATH = REPOSITORY_ROOT / "configs/scenarios/core-run-town04.yaml"


@pytest.mark.integration
@pytest.mark.traffic
def test_real_native_engine_fake_carla_runs_200_ticks_and_stops() -> None:
    async def exercise() -> None:
        experiment_id = uuid4()
        scenario = load_scenario(SCENARIO_PATH, apply_environment=False)
        path_updates = {}
        for field in ("network_path", "routes_path", "signals_path"):
            path = Path(str(getattr(scenario.traffic_engine, field)))
            path_updates[field] = str(path if path.is_absolute() else REPOSITORY_ROOT / path)
        scenario = scenario.model_copy(
            update={"traffic_engine": scenario.traffic_engine.model_copy(update=path_updates)}
        )
        traffic = NativeTrafficEngine(experiment_id)
        carla = FakeCarlaPort()
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
        )

        await manager.prepare(experiment_id)
        await manager.start()
        for _ in range(200):
            await manager.run_tick()
        await manager.stop("INTEGRATION_COMPLETE")

        assert manager.simulation_time_ms == 10_000
        assert len(logger.frames) == 200
        assert logger.frames[-1].traffic.sequence == 200
        assert repository.statuses[experiment_id] is ExperimentStatus.COMPLETED
        assert traffic.health().status.value == "UNAVAILABLE"
        assert carla.closed

    asyncio.run(exercise())
