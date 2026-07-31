from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from trafficverse.maps.sumo_display import (
    SUMO_INTERNAL_LANE_ROLE,
    SUMO_JUNCTION_ROLE,
    SUMO_LANE_ROLE,
    SUMO_SIGNAL_ROLE,
    augment_geojson_with_sumo_display,
    sumo_display_features,
)


def _sumo_network() -> str:
    return """<net>
  <edge id="road-a">
    <lane id="road-a_0" speed="13.9" width="3.5" shape="0,0,0 10,0,0"/>
    <lane id="road-a_walk" allow="pedestrian" shape="0,2 10,2"/>
  </edge>
  <edge id=":junction_0" function="internal">
    <lane id=":junction_0_0" speed="8.0" shape="11,1 12,2"/>
  </edge>
  <edge id="road-b"><lane id="road-b_0" speed="13.9" width="3.5" shape="13,3 20,3"/></edge>
  <junction id="junction" type="priority" shape="9,-2 13,-2 13,3 9,3"/>
  <connection from="road-a" to="road-b" fromLane="0" toLane="0" via=":junction_0_0"
              tl="junction" linkIndex="0"/>
</net>
"""


def test_sumo_display_features_include_driving_lanes_internal_links_and_junctions(
    tmp_path: Path,
) -> None:
    network_path = tmp_path / "map.net.xml"
    network_path.write_text(_sumo_network(), encoding="utf-8")

    features = sumo_display_features(network_path)

    roles = [
        cast("dict[str, object]", feature["properties"])["trafficverse_role"]
        for feature in features
    ]
    assert roles.count(SUMO_LANE_ROLE) == 2
    assert roles.count(SUMO_INTERNAL_LANE_ROLE) == 3
    assert roles.count(SUMO_JUNCTION_ROLE) == 1
    assert roles.count(SUMO_SIGNAL_ROLE) == 1
    first_properties = cast("dict[str, object]", features[0]["properties"])
    junction_feature = next(
        feature
        for feature in features
        if cast("dict[str, object]", feature["properties"])["trafficverse_role"]
        == SUMO_JUNCTION_ROLE
    )
    junction_geometry = cast("dict[str, object]", junction_feature["geometry"])
    polygon_coordinates = cast("list[list[list[float]]]", junction_geometry["coordinates"])
    assert first_properties["width_m"] == 3.5
    polygon = polygon_coordinates[0]
    assert polygon[0] == polygon[-1]


def test_augment_geojson_preserves_canonical_features_and_is_idempotent(tmp_path: Path) -> None:
    geojson_path = tmp_path / "network.geojson"
    geojson_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "lane:1",
                        "properties": {"lane_id": "lane:1"},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[0, 0, 0], [1, 0, 0]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    network_path = tmp_path / "map.net.xml"
    network_path.write_text(_sumo_network(), encoding="utf-8")

    augment_geojson_with_sumo_display(geojson_path, network_path)
    first = geojson_path.read_text(encoding="utf-8")
    augment_geojson_with_sumo_display(geojson_path, network_path)

    payload = json.loads(geojson_path.read_text(encoding="utf-8"))
    assert geojson_path.read_text(encoding="utf-8") == first
    assert payload["features"][0]["id"] == "lane:1"
    assert len(payload["features"]) == 8


def test_tracked_town04_geojson_contains_complete_sumo_display_geometry() -> None:
    map_directory = Path(__file__).resolve().parents[3] / "configs/maps/town04"
    payload = json.loads((map_directory / "network.geojson").read_text(encoding="utf-8"))
    properties = [feature.get("properties", {}) for feature in payload["features"]]
    roles = {value.get("trafficverse_role") for value in properties}

    assert {SUMO_LANE_ROLE, SUMO_INTERNAL_LANE_ROLE, SUMO_JUNCTION_ROLE} <= roles
    assert any("sumo_from_lane_id" in value for value in properties)
