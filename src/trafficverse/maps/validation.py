"""Schema, topology, route, signal, and manifest validation."""

import json
from collections import deque
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import yaml
from pydantic import ValidationError

from trafficverse.maps.errors import MapCompileError
from trafficverse.maps.models import NETWORK_SCHEMA_VERSION, RoadNetwork


def load_network(path: Path) -> RoadNetwork:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return RoadNetwork.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise MapCompileError(f"invalid {NETWORK_SCHEMA_VERSION} asset: {path}: {error}") from error


def validate_network(network: RoadNetwork) -> None:
    lane_ids = {lane.lane_id for lane in network.lanes}
    link_ids = {link.link_id for link in network.links}
    signal_ids = {signal.signal_id for signal in network.signals}
    errors: list[str] = []
    for lane in network.lanes:
        references = (*lane.successor_ids, *lane.predecessor_ids)
        references += tuple(
            item for item in (lane.left_lane_id, lane.right_lane_id) if item is not None
        )
        for reference in references:
            if reference not in lane_ids:
                errors.append(f"lane {lane.lane_id} references missing lane {reference}")
    for link in network.links:
        if link.from_lane_id not in lane_ids or link.to_lane_id not in lane_ids:
            errors.append(f"link {link.link_id} has a dangling lane reference")
        if link.signal_id is not None and link.signal_id not in signal_ids:
            errors.append(f"link {link.link_id} references missing signal {link.signal_id}")
    for signal in network.signals:
        missing = set(signal.controlled_link_ids) - link_ids
        if missing:
            errors.append(f"signal {signal.signal_id} references missing links {sorted(missing)}")
    if errors:
        raise MapCompileError("; ".join(sorted(errors)))


def route_is_reachable(network: RoadNetwork, lane_ids: tuple[str, ...]) -> bool:
    if not lane_ids:
        return False
    successors = {lane.lane_id: set(lane.successor_ids) for lane in network.lanes}
    if any(lane_id not in successors for lane_id in lane_ids):
        return False
    return all(
        target in successors[source] for source, target in zip(lane_ids, lane_ids[1:], strict=False)
    )


def shortest_route(network: RoadNetwork, origin: str, minimum_hops: int = 3) -> tuple[str, ...]:
    successors = {lane.lane_id: tuple(sorted(lane.successor_ids)) for lane in network.lanes}
    queue: deque[tuple[str, tuple[str, ...]]] = deque([(origin, (origin,))])
    visited = {origin}
    fallback: tuple[str, ...] = (origin,)
    while queue:
        current, path = queue.popleft()
        fallback = path if len(path) > len(fallback) else fallback
        if len(path) >= minimum_hops + 1:
            return path
        for candidate in successors[current]:
            if candidate not in visited:
                visited.add(candidate)
                queue.append((candidate, (*path, candidate)))
    return fallback


def validate_compiled_bundle(directory: Path, *, expected_routes: int = 50) -> RoadNetwork:
    """Validate semantic cross-file references after manifest checksum validation."""
    network = load_network(directory / "network.json")
    validate_network(network)
    try:
        route_payload = yaml.safe_load((directory / "routes.yaml").read_text(encoding="utf-8"))
        signal_payload = yaml.safe_load((directory / "signals.yaml").read_text(encoding="utf-8"))
        geojson = json.loads((directory / "network.geojson").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, json.JSONDecodeError) as error:
        raise MapCompileError(f"invalid compiled map bundle: {error}") from error
    if not isinstance(route_payload, Mapping) or not isinstance(route_payload.get("routes"), list):
        raise MapCompileError("routes.yaml must contain a routes list")
    routes = cast("list[object]", route_payload["routes"])
    if len(routes) != expected_routes:
        raise MapCompileError(f"expected {expected_routes} routes, found {len(routes)}")
    for index, route in enumerate(routes):
        if not isinstance(route, Mapping) or not isinstance(route.get("lane_ids"), list):
            raise MapCompileError(f"route {index} has no lane_ids list")
        lane_ids = tuple(str(lane_id) for lane_id in cast("list[object]", route["lane_ids"]))
        if not route_is_reachable(network, lane_ids):
            raise MapCompileError(f"route {index} is not reachable")
    if not isinstance(signal_payload, Mapping) or not isinstance(
        signal_payload.get("programs"), list
    ):
        raise MapCompileError("signals.yaml must contain a programs list")
    programs = cast("list[object]", signal_payload["programs"])
    program_ids = {
        str(program["signal_id"])
        for program in programs
        if isinstance(program, Mapping) and "signal_id" in program
    }
    network_signal_ids = {signal.signal_id for signal in network.signals}
    if program_ids != network_signal_ids:
        raise MapCompileError("signal programs do not exactly cover network signals")
    if not isinstance(geojson, Mapping) or not isinstance(geojson.get("features"), list):
        raise MapCompileError("network.geojson must contain a features list")
    features = cast("list[object]", geojson["features"])
    feature_ids = {
        str(feature.get("id"))
        for feature in features
        if isinstance(feature, Mapping)
        and isinstance(feature.get("geometry"), Mapping)
        and cast("Mapping[object, object]", feature["geometry"]).get("type") == "LineString"
    }
    network_lane_ids = {lane.lane_id for lane in network.lanes}
    if feature_ids != network_lane_ids:
        raise MapCompileError("GeoJSON features do not exactly cover network lanes")
    signal_feature_ids = {
        str(feature.get("id"))
        for feature in features
        if isinstance(feature, Mapping)
        and isinstance(feature.get("geometry"), Mapping)
        and cast("Mapping[object, object]", feature["geometry"]).get("type") == "Point"
    }
    if signal_feature_ids != network_signal_ids:
        raise MapCompileError("GeoJSON point features do not exactly cover network signals")
    return network
