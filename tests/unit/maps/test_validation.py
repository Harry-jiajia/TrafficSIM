import pytest
from pydantic import ValidationError

from trafficverse.domain.models import Vector3
from trafficverse.maps.errors import MapCompileError
from trafficverse.maps.models import Lane, LaneLink, RoadNetwork, TrafficSignal
from trafficverse.maps.validation import validate_network


def _lane(identifier: str, *, successors: tuple[str, ...] = ()) -> Lane:
    return Lane(
        lane_id=identifier,
        road_id="1",
        section_index=0,
        source_lane_id=-1,
        length_m=10,
        width_m=3.5,
        speed_limit_mps=10,
        centerline=(Vector3(x=0, y=0), Vector3(x=10, y=0)),
        successor_ids=successors,
    )


def test_validator_rejects_dangling_topology_and_signal_references() -> None:
    network = RoadNetwork(
        map_id="broken",
        lanes=(_lane("a", successors=("missing",)),),
        links=(LaneLink(link_id="link", from_lane_id="a", to_lane_id="missing"),),
        signals=(
            TrafficSignal(
                signal_id="signal",
                opendrive_id="1",
                road_id="1",
                controlled_link_ids=("missing-link",),
            ),
        ),
    )

    with pytest.raises(MapCompileError, match="missing"):
        validate_network(network)


def test_schema_rejects_unknown_fields() -> None:
    payload = _lane("a").model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        Lane.model_validate(payload)
