"""CARLA Python SDK wrapper.

The module deliberately loads ``carla`` lazily so macOS control-plane installs do
not require an unsupported CARLA wheel.
"""

from __future__ import annotations

import importlib
import io
import math
from collections.abc import Sequence
from typing import Any

from trafficverse.adapters.carla.models import (
    CameraCallback,
    RuntimeCameraFrame,
    RuntimeOperationResult,
    RuntimeSpawnRequest,
    RuntimeSpawnResult,
    RuntimeTrafficLight,
    RuntimeTransform,
    RuntimeVersions,
    RuntimeWorldSettings,
)
from trafficverse.domain.enums import TrafficLightColor


class PythonCarlaRuntime:
    """Untyped anti-corruption layer around the third-party CARLA SDK."""

    def __init__(self) -> None:
        self._carla: Any = None
        self._client: Any = None
        self._world: Any = None
        self._camera: Any = None

    def connect(
        self, host: str, port: int, timeout_s: float, worker_threads: int
    ) -> RuntimeVersions:
        try:
            self._carla = importlib.import_module("carla")
        except ImportError as error:
            raise RuntimeError(
                "CARLA Python SDK is unavailable; run this command on the remote "
                "Linux x86_64 Simulation Runtime with the 'carla' extra installed"
            ) from error
        self._client = self._carla.Client(host, port, worker_threads)
        self._client.set_timeout(timeout_s)
        self._world = self._client.get_world()
        client_version = str(self._client.get_client_version())
        server_version = str(self._client.get_server_version())
        return RuntimeVersions(client=client_version, server=server_version)

    def load_world(self, map_name: str) -> None:
        self._world = self._client.load_world(map_name, reset_settings=False)

    def get_world_settings(self) -> RuntimeWorldSettings:
        settings = self._world.get_settings()
        delta = settings.fixed_delta_seconds
        return RuntimeWorldSettings(
            synchronous_mode=bool(settings.synchronous_mode),
            fixed_delta_seconds=None if delta is None else float(delta),
        )

    def apply_world_settings(self, settings: RuntimeWorldSettings) -> None:
        world_settings = self._world.get_settings()
        world_settings.synchronous_mode = settings.synchronous_mode
        world_settings.fixed_delta_seconds = settings.fixed_delta_seconds
        self._world.apply_settings(world_settings)

    def set_weather(self, preset: str) -> None:
        weather = getattr(self._carla.WeatherParameters, preset, None)
        if weather is None:
            raise ValueError(f"unknown CARLA weather preset: {preset}")
        self._world.set_weather(weather)

    def available_blueprints(self, pattern: str) -> tuple[str, ...]:
        library = self._world.get_blueprint_library()
        return tuple(sorted(str(blueprint.id) for blueprint in library.filter(pattern)))

    def _transform(self, value: RuntimeTransform) -> Any:
        return self._carla.Transform(
            self._carla.Location(x=value.x, y=value.y, z=value.z),
            self._carla.Rotation(yaw=math.degrees(value.heading_rad)),
        )

    def spawn_vehicles(
        self, requests: Sequence[RuntimeSpawnRequest]
    ) -> tuple[RuntimeSpawnResult, ...]:
        library = self._world.get_blueprint_library()
        commands = []
        for request in requests:
            blueprint = library.find(request.blueprint_id)
            command = self._carla.command.SpawnActor(blueprint, self._transform(request.transform))
            if hasattr(self._carla.command, "SetAutopilot"):
                command = command.then(
                    self._carla.command.SetAutopilot(self._carla.command.FutureActor, False)
                )
            commands.append(command)
        responses = self._client.apply_batch_sync(commands, False)
        results: list[RuntimeSpawnResult] = []
        for request, response in zip(requests, responses, strict=True):
            error = str(response.error) if response.error else None
            actor_id = None if error else int(response.actor_id)
            if actor_id is not None:
                actor = self._world.get_actor(actor_id)
                if actor is not None:
                    actor.set_autopilot(False)
                    actor.set_simulate_physics(False)
                    actor.set_enable_gravity(False)
            results.append(
                RuntimeSpawnResult(
                    vehicle_id=request.vehicle_id,
                    actor_id=actor_id,
                    error=error,
                )
            )
        return tuple(results)

    def update_actors(
        self, updates: Sequence[tuple[int, RuntimeTransform]]
    ) -> tuple[RuntimeOperationResult, ...]:
        commands = [
            self._carla.command.ApplyTransform(actor_id, self._transform(transform))
            for actor_id, transform in updates
        ]
        return self._operation_results(
            [actor_id for actor_id, _ in updates],
            self._client.apply_batch_sync(commands, False),
        )

    def destroy_actors(self, actor_ids: Sequence[int]) -> tuple[RuntimeOperationResult, ...]:
        commands = [self._carla.command.DestroyActor(actor_id) for actor_id in actor_ids]
        return self._operation_results(actor_ids, self._client.apply_batch_sync(commands, False))

    def existing_actor_ids(self, actor_ids: Sequence[int]) -> frozenset[int]:
        return frozenset(
            actor_id for actor_id in actor_ids if self._world.get_actor(actor_id) is not None
        )

    @staticmethod
    def _operation_results(
        actor_ids: Sequence[int], responses: Sequence[Any]
    ) -> tuple[RuntimeOperationResult, ...]:
        return tuple(
            RuntimeOperationResult(
                actor_id=actor_id,
                error=str(response.error) if response.error else None,
            )
            for actor_id, response in zip(actor_ids, responses, strict=True)
        )

    def freeze_traffic_lights(self, frozen: bool) -> None:
        self._world.freeze_all_traffic_lights(frozen)

    def traffic_lights(self) -> tuple[RuntimeTrafficLight, ...]:
        lights = self._world.get_actors().filter("traffic.traffic_light*")
        return tuple(
            RuntimeTrafficLight(
                actor_id=int(light.id),
                opendrive_id=str(light.get_opendrive_id()),
                frozen=bool(light.is_frozen()),
            )
            for light in lights
        )

    def update_traffic_lights(
        self, updates: Sequence[tuple[int, TrafficLightColor]]
    ) -> tuple[RuntimeOperationResult, ...]:
        state_by_color = {
            TrafficLightColor.RED: self._carla.TrafficLightState.Red,
            TrafficLightColor.YELLOW: self._carla.TrafficLightState.Yellow,
            TrafficLightColor.GREEN: self._carla.TrafficLightState.Green,
            TrafficLightColor.OFF: self._carla.TrafficLightState.Off,
        }
        if hasattr(self._carla.command, "SetTrafficLightState"):
            commands = [
                self._carla.command.SetTrafficLightState(actor_id, state_by_color[color])
                for actor_id, color in updates
            ]
            return self._operation_results(
                [actor_id for actor_id, _ in updates],
                self._client.apply_batch_sync(commands, False),
            )
        results = []
        for actor_id, color in updates:
            actor = self._world.get_actor(actor_id)
            if actor is None:
                results.append(RuntimeOperationResult(actor_id, "actor not found"))
            else:
                actor.set_state(state_by_color[color])
                results.append(RuntimeOperationResult(actor_id))
        return tuple(results)

    def start_camera(
        self,
        *,
        mode: str,
        target_actor_id: int | None,
        width: int,
        height: int,
        fps: int,
        jpeg_quality: int,
        callback: CameraCallback,
    ) -> None:
        self.stop_camera()
        blueprint = self._world.get_blueprint_library().find("sensor.camera.rgb")
        blueprint.set_attribute("image_size_x", str(width))
        blueprint.set_attribute("image_size_y", str(height))
        blueprint.set_attribute("sensor_tick", str(1.0 / fps))
        if mode == "FOLLOW":
            transform = self._carla.Transform(
                self._carla.Location(x=-8.0, z=4.0),
                self._carla.Rotation(pitch=-15.0),
            )
            target = self._world.get_actor(target_actor_id)
            self._camera = self._world.spawn_actor(blueprint, transform, attach_to=target)
        else:
            transform = self._carla.Transform(
                self._carla.Location(z=100.0),
                self._carla.Rotation(pitch=-90.0),
            )
            self._camera = self._world.spawn_actor(blueprint, transform)
        camera_id = str(self._camera.id)

        def on_image(image: Any) -> None:
            pillow_image_module = importlib.import_module("PIL.Image")
            raw = bytes(image.raw_data)
            rgba = pillow_image_module.frombytes(
                "RGBA", (int(image.width), int(image.height)), raw, "raw", "BGRA"
            )
            stream = io.BytesIO()
            rgba.convert("RGB").save(stream, format="JPEG", quality=jpeg_quality)
            callback(
                RuntimeCameraFrame(
                    camera_id=camera_id,
                    carla_frame=int(image.frame),
                    simulation_time_ms=round(float(image.timestamp) * 1000),
                    width=int(image.width),
                    height=int(image.height),
                    jpeg_bytes=stream.getvalue(),
                )
            )

        self._camera.listen(on_image)

    def stop_camera(self) -> None:
        if self._camera is not None:
            if self._camera.is_listening:
                self._camera.stop()
            self._camera.destroy()
            self._camera = None

    def tick(self, timeout_s: float) -> int:
        return int(self._world.tick(timeout_s))

    def actor_count(self) -> int:
        return len(self._world.get_actors())

    def disconnect(self) -> None:
        self._client = None
        self._world = None
        self._carla = None
