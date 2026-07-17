"""Lazy TraCI SDK wrapper for an externally started SUMO server."""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from typing import Any

from trafficverse.adapters.sumo.models import SumoTrafficLightSample, SumoVehicleSample
from trafficverse.config.models import SumoConfig

_VERSION_PATTERN = re.compile(r"(?P<version>\d+\.\d+\.\d+)")


class PythonSumoRuntime:
    """Keep all untyped TraCI objects inside the adapter boundary."""

    def __init__(self) -> None:
        self._connection: Any | None = None

    def connect(self, config: SumoConfig) -> str:
        traci = self._load_traci()
        self._connection = traci.connect(
            port=config.port,
            host=config.host,
            numRetries=config.connect_retries,
            proc=None,
        )
        _api_version, description = self._connection.getVersion()
        match = _VERSION_PATTERN.search(str(description))
        return match.group("version") if match is not None else str(description)

    def simulation_step(self, target_time_s: float) -> None:
        self._require_connection().simulationStep(target_time_s)

    def simulation_time_s(self) -> float:
        return float(self._require_connection().simulation.getTime())

    def departed_vehicle_ids(self) -> tuple[str, ...]:
        values = self._require_connection().simulation.getDepartedIDList()
        return tuple(sorted(str(value) for value in values))

    def arrived_vehicle_ids(self) -> tuple[str, ...]:
        values = self._require_connection().simulation.getArrivedIDList()
        return tuple(sorted(str(value) for value in values))

    def vehicle_samples(self) -> tuple[SumoVehicleSample, ...]:
        vehicle_api = self._require_connection().vehicle
        samples = []
        for vehicle_id in sorted(str(value) for value in vehicle_api.getIDList()):
            x_m, y_m, z_m = vehicle_api.getPosition3D(vehicle_id)
            samples.append(
                SumoVehicleSample(
                    vehicle_id=vehicle_id,
                    x_m=float(x_m),
                    y_m=float(y_m),
                    z_m=float(z_m),
                    speed_mps=max(0.0, float(vehicle_api.getSpeed(vehicle_id))),
                    acceleration_mps2=float(vehicle_api.getAcceleration(vehicle_id)),
                    angle_deg=float(vehicle_api.getAngle(vehicle_id)),
                    lane_id=str(vehicle_api.getLaneID(vehicle_id)),
                    route_id=str(vehicle_api.getRouteID(vehicle_id)),
                )
            )
        return tuple(samples)

    def traffic_light_samples(self) -> tuple[SumoTrafficLightSample, ...]:
        traffic_lights = self._require_connection().trafficlight
        phases: dict[str, str] = {}
        for traffic_light_id in sorted(str(value) for value in traffic_lights.getIDList()):
            state = str(traffic_lights.getRedYellowGreenState(traffic_light_id))
            for link_index, state_character in enumerate(state):
                parameter = str(
                    traffic_lights.getParameter(
                        traffic_light_id,
                        f"linkSignalID:{link_index}",
                    )
                )
                for opendrive_id in parameter.split():
                    phase = _phase_name(state_character)
                    previous = phases.get(opendrive_id)
                    phases[opendrive_id] = _strictest_phase(previous, phase)
        return tuple(
            SumoTrafficLightSample(signal_id=f"signal:{signal_id}", phase=phase)
            for signal_id, phase in sorted(phases.items())
        )

    def set_vehicle_speed(self, vehicle_id: str, speed_mps: float) -> None:
        self._require_connection().vehicle.setSpeed(vehicle_id, speed_mps)

    def set_vehicle_acceleration(
        self, vehicle_id: str, acceleration_mps2: float, duration_s: float
    ) -> None:
        self._require_connection().vehicle.setAcceleration(
            vehicle_id,
            acceleration_mps2,
            duration_s,
        )

    def change_lane_relative(self, vehicle_id: str, direction: int, duration_s: float) -> None:
        self._require_connection().vehicle.changeLaneRelative(vehicle_id, direction, duration_s)

    def close(self) -> None:
        if self._connection is None:
            return
        try:
            self._connection.close(False)
        finally:
            self._connection = None

    @staticmethod
    def _load_traci() -> Any:
        try:
            return importlib.import_module("traci")
        except ModuleNotFoundError:
            tools_path = Path("/usr/share/sumo/tools")
            if tools_path.is_dir() and str(tools_path) not in sys.path:
                sys.path.append(str(tools_path))
            return importlib.import_module("traci")

    def _require_connection(self) -> Any:
        if self._connection is None:
            raise RuntimeError("TraCI connection is not open")
        return self._connection


def _phase_name(value: str) -> str:
    if value in {"r", "R"}:
        return "RED"
    if value in {"y", "Y"}:
        return "YELLOW"
    if value in {"g", "G"}:
        return "GREEN"
    return "OFF"


def _strictest_phase(previous: str | None, current: str) -> str:
    priority = {"OFF": 0, "GREEN": 1, "YELLOW": 2, "RED": 3}
    if previous is None or priority[current] > priority[previous]:
        return current
    return previous
