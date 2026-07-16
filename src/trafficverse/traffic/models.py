"""Native traffic demand and fixed-signal configuration models."""

from typing import Literal

from pydantic import Field, field_validator

from trafficverse.domain.enums import TrafficLightColor
from trafficverse.domain.models.common import StrictModel


class RouteDemand(StrictModel):
    route_id: str = Field(min_length=1)
    lane_ids: tuple[str, ...] = Field(min_length=1)
    vehicle_id: str = Field(min_length=1)
    depart_ms: int = Field(ge=0)
    desired_speed_mps: float = Field(gt=0.0)


class RouteCatalog(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    routes: tuple[RouteDemand, ...] = Field(min_length=1)

    @field_validator("routes")
    @classmethod
    def identifiers_must_be_unique(cls, value: tuple[RouteDemand, ...]) -> tuple[RouteDemand, ...]:
        route_ids = [route.route_id for route in value]
        vehicle_ids = [route.vehicle_id for route in value]
        if len(route_ids) != len(set(route_ids)) or len(vehicle_ids) != len(set(vehicle_ids)):
            raise ValueError("route and vehicle identifiers must be unique")
        return value


class SignalPhase(StrictModel):
    color: TrafficLightColor
    duration_ms: int = Field(gt=0)


class SignalProgram(StrictModel):
    signal_id: str = Field(min_length=1)
    phases: tuple[SignalPhase, ...] = Field(min_length=1)


class SignalCatalog(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    programs: tuple[SignalProgram, ...] = ()
