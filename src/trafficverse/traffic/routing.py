"""Deterministic shortest-path routing over the frozen lane graph."""

import heapq
import math

from trafficverse.maps.models import RoadNetwork


def shortest_path(network: RoadNetwork, origin: str, destination: str) -> tuple[str, ...]:
    """Return a length-weighted Dijkstra path, using lane IDs for stable tie-breaking."""
    lanes = {lane.lane_id: lane for lane in network.lanes}
    if origin not in lanes or destination not in lanes:
        raise ValueError("route endpoint is not present in the network")
    distances: dict[str, float] = dict.fromkeys(lanes, math.inf)
    distances[origin] = 0.0
    previous: dict[str, str] = {}
    queue: list[tuple[float, str]] = [(0.0, origin)]
    while queue:
        distance, lane_id = heapq.heappop(queue)
        if distance != distances[lane_id]:
            continue
        if lane_id == destination:
            break
        for successor in sorted(lanes[lane_id].successor_ids):
            candidate = distance + lanes[successor].length_m
            if candidate < distances[successor]:
                distances[successor] = candidate
                previous[successor] = lane_id
                heapq.heappush(queue, (candidate, successor))
    if not math.isfinite(distances[destination]):
        raise ValueError(f"no route from {origin} to {destination}")
    result = [destination]
    while result[-1] != origin:
        result.append(previous[result[-1]])
    result.reverse()
    return tuple(result)
