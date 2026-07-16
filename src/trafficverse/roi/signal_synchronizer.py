"""Persistent OpenDRIVE to runtime CARLA traffic-light binding."""

from __future__ import annotations

from pathlib import Path

import yaml

from trafficverse.domain.enums import TrafficLightColor
from trafficverse.domain.models import (
    CarlaTrafficLight,
    SignalBinding,
    TrafficLightState,
    TrafficLightUpdate,
)
from trafficverse.maps.validation import load_network
from trafficverse.traffic.models import SignalCatalog


class SignalSynchronizer:
    def __init__(self, bindings: tuple[SignalBinding, ...], *, strict: bool = True) -> None:
        ids = [binding.traffic_signal_id for binding in bindings]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate native signal binding")
        self._bindings = {binding.traffic_signal_id: binding for binding in bindings}
        self._strict = strict
        self._actors_by_signal: dict[str, tuple[int, ...]] | None = None

    @classmethod
    def from_assets(
        cls,
        network_path: Path,
        signals_path: Path,
        *,
        strict: bool = True,
    ) -> SignalSynchronizer:
        network = load_network(network_path)
        signal_payload = yaml.safe_load(signals_path.read_text(encoding="utf-8"))
        catalog = SignalCatalog.model_validate(signal_payload)
        programs = {program.signal_id: program for program in catalog.programs}
        bindings = []
        for signal in network.signals:
            program = programs.get(signal.signal_id)
            if program is None:
                raise ValueError(f"signal has no fixed program: {signal.signal_id}")
            phase_map = {phase.color.value: phase.color for phase in program.phases}
            bindings.append(
                SignalBinding(
                    traffic_signal_id=signal.signal_id,
                    controlled_link_ids=signal.controlled_link_ids,
                    carla_opendrive_ids=(signal.opendrive_id,),
                    phase_map=phase_map,
                )
            )
        return cls(tuple(bindings), strict=strict)

    def initialize(self, traffic_lights: tuple[CarlaTrafficLight, ...]) -> None:
        by_opendrive: dict[str, list[CarlaTrafficLight]] = {}
        for light in traffic_lights:
            by_opendrive.setdefault(light.opendrive_id, []).append(light)
        duplicates = sorted(key for key, values in by_opendrive.items() if len(values) > 1)
        if duplicates:
            raise ValueError(f"duplicate CARLA OpenDRIVE traffic-light IDs: {duplicates}")

        actors_by_signal: dict[str, tuple[int, ...]] = {}
        missing = []
        unfrozen = []
        for signal_id, binding in self._bindings.items():
            actors = []
            for opendrive_id in binding.carla_opendrive_ids:
                candidate_light: CarlaTrafficLight | None = next(
                    iter(by_opendrive.get(opendrive_id, ())), None
                )
                if candidate_light is None:
                    missing.append(opendrive_id)
                    continue
                if not candidate_light.frozen:
                    unfrozen.append(opendrive_id)
                actors.append(candidate_light.actor_id)
            actors_by_signal[signal_id] = tuple(actors)
        if self._strict and (missing or unfrozen):
            raise ValueError(
                f"CARLA signal readiness failed; missing={sorted(missing)}, "
                f"unfrozen={sorted(unfrozen)}"
            )
        self._actors_by_signal = actors_by_signal

    def plan(self, traffic_lights: tuple[TrafficLightState, ...]) -> tuple[TrafficLightUpdate, ...]:
        if self._actors_by_signal is None:
            raise ValueError("CARLA traffic-light bindings are not initialized")
        states = {state.signal_id: state for state in traffic_lights}
        if self._strict and set(states) != set(self._bindings):
            missing = sorted(set(self._bindings) - set(states))
            unknown = sorted(set(states) - set(self._bindings))
            raise ValueError(f"native signal state mismatch; missing={missing}, unknown={unknown}")
        updates: dict[int, TrafficLightColor] = {}
        for signal_id, state in states.items():
            binding = self._bindings.get(signal_id)
            if binding is None:
                continue
            color = binding.phase_map.get(state.phase)
            if color is None:
                raise ValueError(f"unknown phase {state.phase!r} for signal {signal_id}")
            for actor_id in self._actors_by_signal.get(signal_id, ()):
                previous = updates.get(actor_id)
                if previous is not None and previous is not color:
                    raise ValueError(f"conflicting colors for CARLA traffic light {actor_id}")
                updates[actor_id] = color
        return tuple(
            TrafficLightUpdate(carla_actor_id=actor_id, color=color)
            for actor_id, color in sorted(updates.items())
        )
