from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from trafficverse.domain.enums import TrafficLightColor
from trafficverse.domain.models import (
    CarlaTrafficLight,
    SignalBinding,
    TrafficLightState,
)
from trafficverse.maps.validation import load_network
from trafficverse.roi import SignalSynchronizer
from trafficverse.traffic.models import SignalCatalog

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MAP_DIRECTORY = REPOSITORY_ROOT / "configs/maps/town04"


def _binding() -> SignalBinding:
    return SignalBinding(
        traffic_signal_id="signal:1",
        controlled_link_ids=("link:1",),
        carla_opendrive_ids=("1",),
        phase_map={color.value: color for color in TrafficLightColor},
    )


def test_signal_state_is_mapped_to_runtime_actor_in_same_tick() -> None:
    synchronizer = SignalSynchronizer((_binding(),))
    synchronizer.initialize((CarlaTrafficLight(actor_id=42, opendrive_id="1", frozen=True),))

    updates = synchronizer.plan(
        (TrafficLightState(signal_id="signal:1", simulation_time_ms=50, phase="RED"),)
    )

    assert len(updates) == 1
    assert updates[0].carla_actor_id == 42
    assert updates[0].color is TrafficLightColor.RED


@pytest.mark.parametrize(
    "lights, message",
    [
        ((), "missing"),
        ((CarlaTrafficLight(actor_id=42, opendrive_id="1", frozen=False),), "unfrozen"),
    ],
)
def test_missing_or_unfrozen_binding_fails_readiness(
    lights: tuple[CarlaTrafficLight, ...], message: str
) -> None:
    synchronizer = SignalSynchronizer((_binding(),))

    with pytest.raises(ValueError, match=message):
        synchronizer.initialize(lights)


def test_town04_assets_resolve_every_native_signal_without_runtime_guessing() -> None:
    synchronizer = SignalSynchronizer.from_assets(
        MAP_DIRECTORY / "network.json",
        MAP_DIRECTORY / "signals.yaml",
    )
    network = load_network(MAP_DIRECTORY / "network.json")
    lights = tuple(
        CarlaTrafficLight(actor_id=index + 1, opendrive_id=signal.opendrive_id, frozen=True)
        for index, signal in enumerate(network.signals)
    )
    catalog = SignalCatalog.model_validate(
        yaml.safe_load((MAP_DIRECTORY / "signals.yaml").read_text(encoding="utf-8"))
    )
    states = tuple(
        TrafficLightState(
            signal_id=program.signal_id,
            simulation_time_ms=50,
            phase=program.phases[0].color.value,
        )
        for program in catalog.programs
    )

    synchronizer.initialize(lights)
    updates = synchronizer.plan(states)

    assert len(updates) == len(network.signals)
