"""Build display-only road geometry from a SUMO network asset."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ElementTree
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from trafficverse.maps.errors import MapCompileError

SUMO_LANE_ROLE = "sumo_lane"
SUMO_INTERNAL_LANE_ROLE = "sumo_internal_lane"
SUMO_JUNCTION_ROLE = "sumo_junction"
SUMO_SIGNAL_ROLE = "sumo_signal"
SUMO_DISPLAY_ROLES = frozenset(
    {SUMO_LANE_ROLE, SUMO_INTERNAL_LANE_ROLE, SUMO_JUNCTION_ROLE, SUMO_SIGNAL_ROLE}
)


def augment_geojson_with_sumo_display(geojson_path: Path, sumo_network_path: Path) -> None:
    """Add deterministic SUMO lane and junction geometry without replacing canonical features."""
    try:
        payload = json.loads(geojson_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MapCompileError(f"invalid display GeoJSON: {geojson_path}: {error}") from error
    if not isinstance(payload, Mapping) or not isinstance(payload.get("features"), list):
        raise MapCompileError("display GeoJSON must contain a features list")
    existing_features = cast("list[object]", payload["features"])
    canonical_features = [
        feature for feature in existing_features if _feature_role(feature) not in SUMO_DISPLAY_ROLES
    ]
    features = [*canonical_features, *sumo_display_features(sumo_network_path)]
    output = {"type": "FeatureCollection", "features": features}
    geojson_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sumo_display_features(sumo_network_path: Path) -> list[dict[str, object]]:
    """Return passenger-lane paths and junction polygons from a SUMO ``.net.xml`` file."""
    try:
        root = ElementTree.parse(sumo_network_path).getroot()
    except (OSError, ElementTree.ParseError) as error:
        raise MapCompileError(f"invalid SUMO network: {sumo_network_path}: {error}") from error

    features: list[dict[str, object]] = []
    lane_shapes: dict[str, tuple[list[list[float]], float]] = {}
    for edge in root.findall("edge"):
        internal = edge.attrib.get("function") == "internal"
        role = SUMO_INTERNAL_LANE_ROLE if internal else SUMO_LANE_ROLE
        for lane in edge.findall("lane"):
            if not _allows_passenger(lane):
                continue
            lane_id = lane.attrib.get("id")
            coordinates = _parse_shape(lane.attrib.get("shape", ""))
            if lane_id is None or len(coordinates) < 2:
                continue
            width_m = _float_attribute(lane, "width", 3.2)
            lane_shapes[lane_id] = (coordinates, width_m)
            features.append(
                {
                    "type": "Feature",
                    "id": f"display:sumo-lane:{lane_id}",
                    "properties": {
                        "trafficverse_role": role,
                        "sumo_lane_id": lane_id,
                        "sumo_edge_id": edge.attrib.get("id", ""),
                        "speed_limit_mps": _float_attribute(lane, "speed", 0.0),
                        "width_m": width_m,
                    },
                    "geometry": {"type": "LineString", "coordinates": coordinates},
                }
            )

    for index, connection in enumerate(root.findall("connection")):
        from_lane_id = _connection_lane_id(connection, "from", "fromLane")
        to_lane_id = _connection_lane_id(connection, "to", "toLane")
        via_lane_id = connection.attrib.get("via")
        lane_chain = [from_lane_id, *([via_lane_id] if via_lane_id else []), to_lane_id]
        for segment, (source_id, target_id) in enumerate(
            zip(lane_chain, lane_chain[1:], strict=False)
        ):
            source = lane_shapes.get(source_id)
            target = lane_shapes.get(target_id)
            if source is None or target is None:
                continue
            source_shape, source_width_m = source
            target_shape, target_width_m = target
            start = source_shape[-1]
            end = target_shape[0]
            if start == end:
                continue
            features.append(
                {
                    "type": "Feature",
                    "id": f"display:sumo-connection:{index}:{segment}",
                    "properties": {
                        "trafficverse_role": SUMO_INTERNAL_LANE_ROLE,
                        "sumo_from_lane_id": source_id,
                        "sumo_to_lane_id": target_id,
                        "width_m": min(source_width_m, target_width_m),
                    },
                    "geometry": {"type": "LineString", "coordinates": [start, end]},
                }
            )

    for junction in root.findall("junction"):
        junction_id = junction.attrib.get("id")
        coordinates = _parse_shape(junction.attrib.get("shape", ""))
        if junction_id is None or len(coordinates) < 3:
            continue
        if coordinates[0] != coordinates[-1]:
            coordinates.append(coordinates[0])
        features.append(
            {
                "type": "Feature",
                "id": f"display:sumo-junction:{junction_id}",
                "properties": {
                    "trafficverse_role": SUMO_JUNCTION_ROLE,
                    "sumo_junction_id": junction_id,
                    "sumo_junction_type": junction.attrib.get("type", "unknown"),
                },
                "geometry": {"type": "Polygon", "coordinates": [coordinates]},
            }
        )
    signal_points: dict[str, list[float]] = {}
    for connection in root.findall("connection"):
        traffic_light_id = connection.attrib.get("tl")
        link_index = connection.attrib.get("linkIndex")
        if traffic_light_id is None or link_index is None:
            continue
        incoming_lane_id = _connection_lane_id(connection, "from", "fromLane")
        incoming_lane = lane_shapes.get(incoming_lane_id)
        if incoming_lane is None:
            continue
        signal_id = f"sumo-tls:{traffic_light_id}:{link_index}"
        signal_points.setdefault(signal_id, incoming_lane[0][-1])
    for signal_id, signal_coordinates in sorted(signal_points.items()):
        features.append(
            {
                "type": "Feature",
                "id": f"display:{signal_id}",
                "properties": {
                    "trafficverse_role": SUMO_SIGNAL_ROLE,
                    "signal_id": signal_id,
                },
                "geometry": {"type": "Point", "coordinates": signal_coordinates},
            }
        )
    return features


def sumo_display_geojson(sumo_network_path: Path) -> dict[str, object]:
    """Return a complete display-only GeoJSON document for a native SUMO network."""

    return {"type": "FeatureCollection", "features": sumo_display_features(sumo_network_path)}


def _feature_role(feature: object) -> str | None:
    if not isinstance(feature, Mapping) or not isinstance(feature.get("properties"), Mapping):
        return None
    properties = cast("Mapping[object, object]", feature["properties"])
    role = properties.get("trafficverse_role")
    return str(role) if role is not None else None


def _allows_passenger(lane: ElementTree.Element) -> bool:
    allowed = set(lane.attrib.get("allow", "").split())
    disallowed = set(lane.attrib.get("disallow", "").split())
    return "passenger" in allowed if allowed else "passenger" not in disallowed


def _connection_lane_id(
    connection: ElementTree.Element, edge_attribute: str, lane_attribute: str
) -> str:
    edge_id = connection.attrib.get(edge_attribute, "")
    lane_index = connection.attrib.get(lane_attribute, "")
    return f"{edge_id}_{lane_index}"


def _parse_shape(shape: str) -> list[list[float]]:
    coordinates: list[list[float]] = []
    for raw_point in shape.split():
        try:
            values = [float(value) for value in raw_point.split(",")]
        except ValueError as error:
            raise MapCompileError(f"invalid SUMO shape coordinate: {raw_point}") from error
        if len(values) < 2:
            raise MapCompileError(f"invalid SUMO shape coordinate: {raw_point}")
        coordinates.append([values[0], values[1], values[2] if len(values) > 2 else 0.0])
    return coordinates


def _float_attribute(element: ElementTree.Element, name: str, default: float) -> float:
    value = element.attrib.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as error:
        raise MapCompileError(f"invalid SUMO {name} value: {value}") from error
