"""Production CARLA Port implementation for the local CARLA server."""

from __future__ import annotations

import math
import threading
from collections.abc import Sequence
from dataclasses import dataclass

from trafficverse.adapters.carla.models import (
    CarlaRuntime,
    RuntimeOperationResult,
    RuntimeSpawnRequest,
    RuntimeTransform,
    RuntimeWorldSettings,
)
from trafficverse.adapters.carla.runtime import PythonCarlaRuntime
from trafficverse.config.models import CarlaConfig, WeatherConfig
from trafficverse.domain.enums import ComponentStatus, ErrorCode
from trafficverse.domain.errors import TrafficVerseError
from trafficverse.domain.models import (
    ActorSpawnResult,
    CarlaFrame,
    CarlaTrafficLight,
    ComponentHealth,
    TrafficLightUpdate,
)
from trafficverse.ports.simulation import ActorTransform, RenderVehicleSpec


@dataclass(frozen=True, slots=True)
class CarlaDiagnostics:
    client_version: str | None
    server_version: str | None
    connected: bool
    world_loaded: bool
    owned_actor_count: int
    last_carla_frame: int


class CarlaAdapter:
    """Own CARLA lifecycle, deterministic actor batches, and the authoritative tick."""

    def __init__(self, runtime: CarlaRuntime | None = None) -> None:
        self._runtime = runtime or PythonCarlaRuntime()
        self._config: CarlaConfig | None = None
        self._original_settings: RuntimeWorldSettings | None = None
        self._client_version: str | None = None
        self._server_version: str | None = None
        self._connected = False
        self._world_loaded = False
        self._closed = False
        self._vehicle_actors: dict[str, int] = {}
        self._owned_actor_ids: set[int] = set()
        self._tick_thread_id: int | None = None
        self._last_carla_frame = -1
        self._last_target_time_ms = 0

    def connect(self, config: CarlaConfig) -> None:
        try:
            versions = self._runtime.connect(
                config.host,
                config.port,
                config.timeout_s,
                config.worker_threads,
            )
        except Exception as error:
            raise TrafficVerseError(
                ErrorCode.CARLA_CONNECTION_FAILED,
                f"unable to connect to local CARLA at {config.host}:{config.port}: {error}",
            ) from error
        self._client_version = versions.client
        self._server_version = versions.server
        if (
            versions.client != config.expected_version
            or versions.server != config.expected_version
            or versions.client != versions.server
        ):
            self._runtime.disconnect()
            raise TrafficVerseError(
                ErrorCode.CARLA_VERSION_MISMATCH,
                "CARLA client/server versions must exactly match the configured version",
                details={
                    "expected": config.expected_version,
                    "client": versions.client,
                    "server": versions.server,
                },
            )
        self._config = config
        self._connected = True
        self._closed = False

    def load_world(self, map_name: str, weather: WeatherConfig) -> None:
        config = self._require_config()
        try:
            self._runtime.load_world(map_name)
            self._original_settings = self._runtime.get_world_settings()
            self._world_loaded = True
            requested = RuntimeWorldSettings(
                synchronous_mode=True,
                fixed_delta_seconds=config.step_ms / 1000.0,
            )
            self._runtime.apply_world_settings(requested)
            actual = self._runtime.get_world_settings()
            if not actual.synchronous_mode or not math.isclose(
                actual.fixed_delta_seconds or -1.0,
                requested.fixed_delta_seconds or -2.0,
                abs_tol=1e-9,
            ):
                raise TrafficVerseError(
                    ErrorCode.CARLA_SYNC_MISMATCH,
                    "CARLA did not accept synchronous fixed-delta settings",
                )
            self._runtime.set_weather(weather.preset)
            self._runtime.freeze_traffic_lights(True)
        except TrafficVerseError:
            raise
        except Exception as error:
            raise TrafficVerseError(
                ErrorCode.CARLA_OPERATION_FAILED,
                f"failed to load CARLA world {map_name}: {error}",
            ) from error

    def spawn_vehicle(self, spec: RenderVehicleSpec) -> int:
        result = self.spawn_vehicles((spec,))[0]
        if result.actor_id is None:
            raise TrafficVerseError(
                ErrorCode.CARLA_OPERATION_FAILED,
                f"failed to spawn {result.vehicle_id}: {result.error}",
            )
        return result.actor_id

    def spawn_vehicles(self, specs: Sequence[RenderVehicleSpec]) -> tuple[ActorSpawnResult, ...]:
        config = self._require_world()
        if len({spec.vehicle_id for spec in specs}) != len(specs):
            raise TrafficVerseError(
                ErrorCode.CARLA_OPERATION_FAILED,
                "spawn batch contains duplicate vehicle IDs",
            )
        available = self._runtime.available_blueprints(config.blueprint_filter)
        if not available:
            raise TrafficVerseError(
                ErrorCode.CARLA_OPERATION_FAILED,
                f"no CARLA blueprints match {config.blueprint_filter}",
            )
        requests = {
            spec.vehicle_id: RuntimeSpawnRequest(
                vehicle_id=spec.vehicle_id,
                blueprint_id=self._resolve_blueprint(spec.blueprint_id, available),
                transform=RuntimeTransform(
                    x=spec.position.x,
                    y=spec.position.y,
                    z=spec.position.z,
                    heading_rad=spec.heading_rad,
                ),
            )
            for spec in specs
        }
        pending = dict(requests)
        successes: dict[str, int] = {}
        errors: dict[str, str] = {}
        for _ in range(config.spawn_retries + 1):
            if not pending:
                break
            batch = tuple(pending[vehicle_id] for vehicle_id in sorted(pending))
            results = self._runtime.spawn_vehicles(batch)
            seen = {result.vehicle_id for result in results}
            if seen != set(pending):
                raise TrafficVerseError(
                    ErrorCode.CARLA_OPERATION_FAILED,
                    "CARLA spawn response does not match the request batch",
                )
            for result in results:
                if result.actor_id is not None and result.error is None:
                    successes[result.vehicle_id] = result.actor_id
                    self._vehicle_actors[result.vehicle_id] = result.actor_id
                    self._owned_actor_ids.add(result.actor_id)
                    pending.pop(result.vehicle_id, None)
                    errors.pop(result.vehicle_id, None)
                else:
                    errors[result.vehicle_id] = result.error or "unknown CARLA error"
        return tuple(
            ActorSpawnResult(
                vehicle_id=spec.vehicle_id,
                success=spec.vehicle_id in successes,
                actor_id=successes.get(spec.vehicle_id),
                error=None if spec.vehicle_id in successes else errors[spec.vehicle_id],
            )
            for spec in specs
        )

    def _resolve_blueprint(self, requested: str, available: tuple[str, ...]) -> str:
        config = self._require_config()
        if requested in available:
            return requested
        for fallback in config.fallback_blueprints:
            if fallback in available:
                return fallback
        return available[0]

    def update_actors(self, updates: Sequence[ActorTransform]) -> None:
        self._require_world()
        results = self._runtime.update_actors(
            tuple(
                (
                    update.actor_id,
                    RuntimeTransform(
                        update.position.x,
                        update.position.y,
                        update.position.z,
                        update.heading_rad,
                    ),
                )
                for update in updates
            )
        )
        self._raise_batch_errors("update actors", results)

    def destroy_actors(self, actor_ids: Sequence[int]) -> None:
        self._require_world()
        owned = tuple(sorted(set(actor_ids) & self._owned_actor_ids))
        if not owned:
            return
        results = self._runtime.destroy_actors(owned)
        self._raise_batch_errors("destroy actors", results)
        for actor_id in owned:
            self._owned_actor_ids.discard(actor_id)
        self._vehicle_actors = {
            vehicle_id: actor_id
            for vehicle_id, actor_id in self._vehicle_actors.items()
            if actor_id not in owned
        }

    def existing_actor_ids(self, actor_ids: Sequence[int]) -> frozenset[int]:
        self._require_world()
        requested = frozenset(actor_ids)
        existing = self._runtime.existing_actor_ids(actor_ids)
        missing = requested - existing
        self._owned_actor_ids.difference_update(missing)
        self._vehicle_actors = {
            vehicle_id: actor_id
            for vehicle_id, actor_id in self._vehicle_actors.items()
            if actor_id not in missing
        }
        return existing

    @staticmethod
    def _raise_batch_errors(operation: str, results: Sequence[RuntimeOperationResult]) -> None:
        failed = [str(result.error) for result in results if result.error]
        if failed:
            raise TrafficVerseError(
                ErrorCode.CARLA_OPERATION_FAILED,
                f"CARLA {operation} failed: {'; '.join(failed)}",
            )

    def update_traffic_lights(self, updates: Sequence[TrafficLightUpdate]) -> None:
        self._require_world()
        results = self._runtime.update_traffic_lights(
            tuple((update.carla_actor_id, update.color) for update in updates)
        )
        self._raise_batch_errors("update traffic lights", results)

    def traffic_lights(self) -> tuple[CarlaTrafficLight, ...]:
        self._require_world()
        return tuple(
            CarlaTrafficLight(
                actor_id=light.actor_id,
                opendrive_id=light.opendrive_id,
                frozen=light.frozen,
            )
            for light in self._runtime.traffic_lights()
        )

    def actor_count(self) -> int:
        """Return the remote world count for smoke-test leak checks."""
        self._require_config()
        return self._runtime.actor_count()

    def tick(self, target_time_ms: int) -> CarlaFrame:
        config = self._require_world()
        expected_target_time_ms = self._last_target_time_ms + config.step_ms
        if target_time_ms != expected_target_time_ms:
            raise TrafficVerseError(
                ErrorCode.CARLA_SYNC_MISMATCH,
                "CARLA target time must advance by exactly the configured fixed step",
                details={
                    "expected_ms": str(expected_target_time_ms),
                    "actual_ms": str(target_time_ms),
                },
            )
        thread_id = threading.get_ident()
        if self._tick_thread_id is None:
            self._tick_thread_id = thread_id
        elif self._tick_thread_id != thread_id:
            raise TrafficVerseError(
                ErrorCode.CARLA_OPERATION_FAILED,
                "CARLA tick ownership cannot move between threads",
            )
        carla_frame = self._runtime.tick(config.timeout_s)
        if carla_frame <= self._last_carla_frame:
            raise TrafficVerseError(
                ErrorCode.CARLA_OPERATION_FAILED,
                "CARLA frame number must increase monotonically",
            )
        self._last_carla_frame = carla_frame
        self._last_target_time_ms = target_time_ms
        return CarlaFrame(
            simulation_time_ms=target_time_ms,
            carla_frame=carla_frame,
            actor_count=self._runtime.actor_count(),
        )

    def health(self) -> ComponentHealth:
        if self._connected and not self._closed:
            return ComponentHealth(
                component="carla",
                status=ComponentStatus.HEALTHY,
                version=self._server_version,
                message="local CARLA connected",
            )
        return ComponentHealth(
            component="carla",
            status=ComponentStatus.UNAVAILABLE,
            version=self._server_version,
            message="local CARLA disconnected",
        )

    def diagnostics(self) -> CarlaDiagnostics:
        return CarlaDiagnostics(
            client_version=self._client_version,
            server_version=self._server_version,
            connected=self._connected and not self._closed,
            world_loaded=self._world_loaded,
            owned_actor_count=len(self._owned_actor_ids),
            last_carla_frame=self._last_carla_frame,
        )

    def close(self) -> None:
        if self._closed:
            return
        first_error: Exception | None = None
        if self._owned_actor_ids:
            try:
                results = self._runtime.destroy_actors(tuple(sorted(self._owned_actor_ids)))
                self._raise_batch_errors("cleanup actors", results)
            except Exception as error:
                first_error = first_error or error
        if self._world_loaded:
            try:
                self._runtime.freeze_traffic_lights(False)
                if self._original_settings is not None:
                    self._runtime.apply_world_settings(self._original_settings)
            except Exception as error:
                first_error = first_error or error
        try:
            self._runtime.disconnect()
        except Exception as error:
            first_error = first_error or error
        self._vehicle_actors.clear()
        self._owned_actor_ids.clear()
        self._connected = False
        self._world_loaded = False
        self._closed = True
        if first_error is not None:
            raise TrafficVerseError(
                ErrorCode.CARLA_OPERATION_FAILED,
                f"CARLA cleanup failed: {first_error}",
            ) from first_error

    def _require_config(self) -> CarlaConfig:
        if self._config is None or not self._connected or self._closed:
            raise TrafficVerseError(
                ErrorCode.CARLA_CONNECTION_FAILED,
                "CARLA adapter is not connected",
            )
        return self._config

    def _require_world(self) -> CarlaConfig:
        config = self._require_config()
        if not self._world_loaded:
            raise TrafficVerseError(
                ErrorCode.CARLA_OPERATION_FAILED,
                "CARLA world is not loaded",
            )
        return config
