"""Vehicle, signal, control, and camera contracts."""

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from trafficverse.domain.enums import (
    AutomationLevel,
    LaneChangeDirection,
    TrafficLightColor,
    VehicleAction,
)
from trafficverse.domain.models.common import StrictModel, Vector3


class VehicleState(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    experiment_id: UUID
    vehicle_id: str = Field(min_length=1)
    simulation_time_ms: int = Field(ge=0)
    sequence: int = Field(ge=0)
    automation_level: AutomationLevel
    position: Vector3
    speed_mps: float = Field(ge=0.0)
    acceleration_mps2: float
    heading_rad: float
    lane_id: str = Field(min_length=1)
    target_lane_id: str | None = None
    controller_id: str = Field(min_length=1)
    action: VehicleAction
    risk_score: float = Field(ge=0.0, le=1.0)
    route_id: str | None = None


class TrafficLightState(StrictModel):
    signal_id: str = Field(min_length=1)
    simulation_time_ms: int = Field(ge=0)
    phase: str = Field(min_length=1)
    remaining_ms: int | None = Field(default=None, ge=0)


class SignalBinding(StrictModel):
    traffic_signal_id: str = Field(min_length=1)
    controlled_link_ids: tuple[str, ...] = Field(min_length=1)
    carla_opendrive_ids: tuple[str, ...] = Field(min_length=1)
    phase_map: dict[str, TrafficLightColor]

    @field_validator("controlled_link_ids")
    @classmethod
    def link_ids_must_be_unique_and_non_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not link_id for link_id in value):
            raise ValueError("controlled link IDs must not be empty")
        if len(set(value)) != len(value):
            raise ValueError("controlled link IDs must be unique")
        return value

    @field_validator("carla_opendrive_ids")
    @classmethod
    def opendrive_ids_must_be_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not signal_id for signal_id in value):
            raise ValueError("CARLA OpenDRIVE signal IDs must not be empty")
        if len(set(value)) != len(value):
            raise ValueError("CARLA OpenDRIVE signal IDs must be unique")
        return value


class CameraFrame(StrictModel):
    camera_id: str = Field(min_length=1)
    carla_frame: int = Field(ge=0)
    simulation_time_ms: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    encoding: Literal["jpeg"] = "jpeg"
    data_base64: str = Field(min_length=1)


class CameraCommand(StrictModel):
    mode: Literal["BIRD_VIEW", "FOLLOW"]
    vehicle_id: str | None = None
    width: int = Field(gt=0, le=4096)
    height: int = Field(gt=0, le=2160)
    fps: int = Field(gt=0, le=60)
    jpeg_quality: int = Field(ge=1, le=100)

    @model_validator(mode="after")
    def follow_requires_vehicle_id(self) -> "CameraCommand":
        if self.mode == "FOLLOW" and not self.vehicle_id:
            raise ValueError("FOLLOW camera mode requires vehicle_id")
        return self


class ActorSpawnResult(StrictModel):
    vehicle_id: str = Field(min_length=1)
    success: bool
    actor_id: int | None = Field(default=None, ge=0)
    error: str | None = None

    @model_validator(mode="after")
    def result_fields_must_match_success(self) -> "ActorSpawnResult":
        if self.success and self.actor_id is None:
            raise ValueError("successful spawn result requires actor_id")
        if not self.success and not self.error:
            raise ValueError("failed spawn result requires error")
        return self


class CarlaTrafficLight(StrictModel):
    """Stable traffic-light identity exposed by the CARLA port."""

    actor_id: int = Field(ge=0)
    opendrive_id: str = Field(min_length=1)
    frozen: bool


class ControlCommand(StrictModel):
    desired_acceleration_mps2: float | None = None
    desired_speed_mps: float | None = Field(default=None, ge=0.0)
    lane_change: LaneChangeDirection = LaneChangeDirection.NONE
    takeover_requested: bool = False
    stop_requested: bool = False

    @model_validator(mode="after")
    def command_must_contain_an_intent(self) -> "ControlCommand":
        if (
            self.desired_acceleration_mps2 is None
            and self.desired_speed_mps is None
            and self.lane_change is LaneChangeDirection.NONE
            and not self.takeover_requested
            and not self.stop_requested
        ):
            raise ValueError("control command must contain at least one intent")
        return self


class TrafficLightUpdate(StrictModel):
    carla_actor_id: int = Field(ge=0)
    color: TrafficLightColor
