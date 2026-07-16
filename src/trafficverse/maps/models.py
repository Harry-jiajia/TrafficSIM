"""Frozen public schema for ``traffic-network/1.0`` assets."""

from typing import Literal

from pydantic import Field, model_validator

from trafficverse.domain.models.common import StrictModel, Vector3

NETWORK_SCHEMA_VERSION = "traffic-network/1.0"
MAP_COMPILER_VERSION = "1.0.0"


class Lane(StrictModel):
    lane_id: str = Field(min_length=1)
    road_id: str = Field(min_length=1)
    section_index: int = Field(ge=0)
    source_lane_id: int
    length_m: float = Field(gt=0.0)
    width_m: float = Field(gt=0.0)
    speed_limit_mps: float = Field(gt=0.0)
    centerline: tuple[Vector3, ...] = Field(min_length=2)
    successor_ids: tuple[str, ...] = ()
    predecessor_ids: tuple[str, ...] = ()
    left_lane_id: str | None = None
    right_lane_id: str | None = None
    junction_id: str | None = None


class LaneLink(StrictModel):
    link_id: str = Field(min_length=1)
    from_lane_id: str = Field(min_length=1)
    to_lane_id: str = Field(min_length=1)
    junction_id: str | None = None
    signal_id: str | None = None
    stop_line_s_m: float | None = Field(default=None, ge=0.0)


class TrafficSignal(StrictModel):
    signal_id: str = Field(min_length=1)
    opendrive_id: str = Field(min_length=1)
    road_id: str = Field(min_length=1)
    controlled_link_ids: tuple[str, ...] = Field(min_length=1)


class RoadNetwork(StrictModel):
    schema_version: Literal["traffic-network/1.0"] = "traffic-network/1.0"
    map_id: str = Field(min_length=1)
    source_format: Literal["OpenDRIVE"] = "OpenDRIVE"
    lanes: tuple[Lane, ...] = Field(min_length=1)
    links: tuple[LaneLink, ...]
    signals: tuple[TrafficSignal, ...] = ()

    @model_validator(mode="after")
    def identifiers_must_be_unique(self) -> "RoadNetwork":
        for label, values in (
            ("lane", [item.lane_id for item in self.lanes]),
            ("link", [item.link_id for item in self.links]),
            ("signal", [item.signal_id for item in self.signals]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} identifier")
        return self
