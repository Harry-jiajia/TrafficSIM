from pathlib import Path
from uuid import uuid4

from tests.fakes import (
    FakeCarlaPort,
    FakeDataLogger,
    FakeEventPublisher,
    FakeExperimentRepository,
    FakeTrafficEnginePort,
)

from trafficverse.bootstrap import AppContainer
from trafficverse.config.loader import load_scenario
from trafficverse.domain.enums import ComponentStatus, ExperimentStatus

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_fake_ports_drive_minimal_external_free_tick() -> None:
    experiment_id = uuid4()
    scenario = load_scenario(
        REPOSITORY_ROOT / "configs" / "scenarios" / "core-run-town04.yaml",
        apply_environment=False,
    )
    traffic = FakeTrafficEnginePort(experiment_id)
    carla = FakeCarlaPort()
    repository = FakeExperimentRepository()
    container = AppContainer(
        traffic=traffic,
        carla=carla,
        experiments=repository,
        events=FakeEventPublisher(),
        data_logger=FakeDataLogger(),
    )

    container.traffic.load(scenario.traffic_engine)
    container.carla.connect(scenario.carla)
    container.carla.load_world("Town04", scenario.weather)
    snapshot = container.traffic.step(50)
    carla_frame = container.carla.tick(50)

    assert snapshot.simulation_time_ms == 50
    assert carla_frame.simulation_time_ms == 50
    assert container.traffic.health().status is ComponentStatus.HEALTHY
    assert container.carla.health().status is ComponentStatus.HEALTHY

    container.carla.close()
    container.traffic.close()
    assert container.traffic.health().status is ComponentStatus.UNAVAILABLE
    assert ExperimentStatus.CREATED.value == "CREATED"
