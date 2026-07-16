"""Windows-side CARLA SDK bridge launched by the macOS TrafficVerse runtime."""

from __future__ import annotations

import argparse
import json
import math
import queue
import socket
import struct
import threading
import traceback
from contextlib import suppress
from typing import Any

import carla

_CAMERA_HEADER = struct.Struct("!4sQdIIII")
_CAMERA_MAGIC = b"TVRG"


class Bridge:
    def __init__(self, control: socket.socket, camera: socket.socket) -> None:
        self._control = control
        self._camera_stream = camera
        self._control_file = control.makefile("rwb", buffering=0)
        self._client: Any = None
        self._world: Any = None
        self._camera: Any = None
        self._camera_frames: queue.Queue[tuple[str, int, float, int, int, bytes] | None] = (
            queue.Queue(maxsize=2)
        )
        self._camera_sender = threading.Thread(
            target=self._send_camera_frames,
            name="trafficverse-camera-sender",
            daemon=True,
        )
        self._camera_sender.start()

    def run(self) -> None:
        while True:
            raw = self._control_file.readline()
            if not raw:
                break
            request = json.loads(raw.decode("utf-8"))
            request_id = int(request["id"])
            operation = str(request["operation"])
            payload = request.get("payload") or {}
            try:
                result = self._dispatch(operation, payload)
                response = {"id": request_id, "ok": True, "result": result}
            except Exception as error:
                response = {
                    "id": request_id,
                    "ok": False,
                    "error": f"{type(error).__name__}: {error}",
                    "traceback": traceback.format_exc(limit=8),
                }
            self._control_file.write(
                json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n"
            )
            if operation == "shutdown":
                break

    def _dispatch(self, operation: str, payload: dict[str, Any]) -> object:
        handler = getattr(self, f"_op_{operation}", None)
        if handler is None:
            raise ValueError(f"unsupported bridge operation: {operation}")
        return handler(payload)

    def _op_connect(self, payload: dict[str, Any]) -> dict[str, str]:
        self._client = carla.Client(
            str(payload["host"]),
            int(payload["port"]),
            int(payload["worker_threads"]),
        )
        self._client.set_timeout(float(payload["timeout_s"]))
        self._world = self._client.get_world()
        return {
            "client": str(self._client.get_client_version()),
            "server": str(self._client.get_server_version()),
        }

    def _op_load_world(self, payload: dict[str, Any]) -> None:
        self._world = self._client.load_world(str(payload["map_name"]), reset_settings=False)

    def _op_get_world_settings(self, payload: dict[str, Any]) -> dict[str, object]:
        del payload
        settings = self._world.get_settings()
        return {
            "synchronous_mode": bool(settings.synchronous_mode),
            "fixed_delta_seconds": settings.fixed_delta_seconds,
        }

    def _op_apply_world_settings(self, payload: dict[str, Any]) -> None:
        settings = self._world.get_settings()
        settings.synchronous_mode = bool(payload["synchronous_mode"])
        settings.fixed_delta_seconds = payload["fixed_delta_seconds"]
        self._world.apply_settings(settings)

    def _op_set_weather(self, payload: dict[str, Any]) -> None:
        preset = str(payload["preset"])
        weather = getattr(carla.WeatherParameters, preset, None)
        if weather is None:
            raise ValueError(f"unknown CARLA weather preset: {preset}")
        self._world.set_weather(weather)

    def _op_blueprints(self, payload: dict[str, Any]) -> list[str]:
        return sorted(
            str(blueprint.id)
            for blueprint in self._world.get_blueprint_library().filter(str(payload["pattern"]))
        )

    def _op_spawn_vehicles(self, payload: dict[str, Any]) -> list[dict[str, object]]:
        library = self._world.get_blueprint_library()
        requests = payload["requests"]
        commands = []
        for request in requests:
            blueprint = library.find(str(request["blueprint_id"]))
            command = carla.command.SpawnActor(blueprint, _transform(request["transform"])).then(
                carla.command.SetAutopilot(carla.command.FutureActor, False)
            )
            commands.append(command)
        responses = self._client.apply_batch_sync(commands, False)
        results = []
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
                {
                    "vehicle_id": str(request["vehicle_id"]),
                    "actor_id": actor_id,
                    "error": error,
                }
            )
        return results

    def _op_update_actors(self, payload: dict[str, Any]) -> list[dict[str, object]]:
        updates = payload["updates"]
        commands = [
            carla.command.ApplyTransform(int(update["actor_id"]), _transform(update["transform"]))
            for update in updates
        ]
        responses = self._client.apply_batch_sync(commands, False)
        return _operation_results([int(item["actor_id"]) for item in updates], responses)

    def _op_destroy_actors(self, payload: dict[str, Any]) -> list[dict[str, object]]:
        actor_ids = [int(value) for value in payload["actor_ids"]]
        responses = self._client.apply_batch_sync(
            [carla.command.DestroyActor(actor_id) for actor_id in actor_ids], False
        )
        return _operation_results(actor_ids, responses)

    def _op_existing_actor_ids(self, payload: dict[str, Any]) -> list[int]:
        return [
            int(actor_id)
            for actor_id in payload["actor_ids"]
            if self._world.get_actor(int(actor_id)) is not None
        ]

    def _op_freeze_traffic_lights(self, payload: dict[str, Any]) -> None:
        frozen = bool(payload["frozen"])
        self._world.freeze_all_traffic_lights(frozen)
        for light in self._world.get_actors().filter("traffic.traffic_light*"):
            light.freeze(frozen)

    def _op_traffic_lights(self, payload: dict[str, Any]) -> list[dict[str, object]]:
        del payload
        return [
            {
                "actor_id": int(light.id),
                "opendrive_id": str(light.get_opendrive_id()),
                "frozen": bool(light.is_frozen()),
            }
            for light in self._world.get_actors().filter("traffic.traffic_light*")
        ]

    def _op_update_traffic_lights(self, payload: dict[str, Any]) -> list[dict[str, object]]:
        state = {
            "RED": carla.TrafficLightState.Red,
            "YELLOW": carla.TrafficLightState.Yellow,
            "GREEN": carla.TrafficLightState.Green,
            "OFF": carla.TrafficLightState.Off,
        }
        updates = payload["updates"]
        if hasattr(carla.command, "SetTrafficLightState"):
            commands = [
                carla.command.SetTrafficLightState(
                    int(update["actor_id"]), state[str(update["color"])]
                )
                for update in updates
            ]
            responses = self._client.apply_batch_sync(commands, False)
            return _operation_results([int(update["actor_id"]) for update in updates], responses)
        results = []
        for update in updates:
            actor_id = int(update["actor_id"])
            actor = self._world.get_actor(actor_id)
            if actor is None:
                results.append({"actor_id": actor_id, "error": "actor not found"})
            else:
                actor.set_state(state[str(update["color"])])
                results.append({"actor_id": actor_id, "error": None})
        return results

    def _op_start_camera(self, payload: dict[str, Any]) -> None:
        self._stop_camera()
        blueprint = self._world.get_blueprint_library().find("sensor.camera.rgb")
        blueprint.set_attribute("image_size_x", str(int(payload["width"])))
        blueprint.set_attribute("image_size_y", str(int(payload["height"])))
        blueprint.set_attribute("sensor_tick", str(1.0 / int(payload["fps"])))
        target = None
        if payload["mode"] == "FOLLOW":
            transform = carla.Transform(
                carla.Location(x=-8.0, z=4.0),
                carla.Rotation(pitch=-15.0),
            )
            target = self._world.get_actor(int(payload["target_actor_id"]))
        else:
            transform = carla.Transform(
                carla.Location(z=100.0),
                carla.Rotation(pitch=-90.0),
            )
        self._camera = self._world.spawn_actor(blueprint, transform, attach_to=target)
        camera_id = str(self._camera.id)

        def receive(image: Any) -> None:
            frame = (
                camera_id,
                int(image.frame),
                float(image.timestamp),
                int(image.width),
                int(image.height),
                bytes(image.raw_data),
            )
            if self._camera_frames.full():
                with suppress(queue.Empty):
                    self._camera_frames.get_nowait()
            with suppress(queue.Full):
                self._camera_frames.put_nowait(frame)

        self._camera.listen(receive)

    def _op_stop_camera(self, payload: dict[str, Any]) -> None:
        del payload
        self._stop_camera()

    def _op_tick(self, payload: dict[str, Any]) -> int:
        return int(self._world.tick(float(payload["timeout_s"])))

    def _op_actor_count(self, payload: dict[str, Any]) -> int:
        del payload
        return len(self._world.get_actors())

    def _op_disconnect(self, payload: dict[str, Any]) -> None:
        del payload
        self._client = None
        self._world = None

    def _op_shutdown(self, payload: dict[str, Any]) -> None:
        del payload
        self._stop_camera()
        self._camera_frames.put(None)

    def _stop_camera(self) -> None:
        if self._camera is not None:
            if self._camera.is_listening:
                self._camera.stop()
            self._camera.destroy()
            self._camera = None

    def _send_camera_frames(self) -> None:
        while True:
            value = self._camera_frames.get()
            if value is None:
                return
            camera_id, frame, timestamp, width, height, raw = value
            camera_id_bytes = camera_id.encode("ascii")
            self._camera_stream.sendall(
                _CAMERA_HEADER.pack(
                    _CAMERA_MAGIC,
                    frame,
                    timestamp,
                    width,
                    height,
                    len(camera_id_bytes),
                    len(raw),
                )
            )
            self._camera_stream.sendall(camera_id_bytes)
            self._camera_stream.sendall(raw)


def _transform(value: dict[str, Any]) -> Any:
    return carla.Transform(
        carla.Location(
            x=float(value["x"]),
            y=float(value["y"]),
            z=float(value["z"]),
        ),
        carla.Rotation(yaw=math.degrees(float(value["heading_rad"]))),
    )


def _operation_results(actor_ids: list[int], responses: list[Any]) -> list[dict[str, object]]:
    return [
        {
            "actor_id": actor_id,
            "error": str(response.error) if response.error else None,
        }
        for actor_id, response in zip(actor_ids, responses, strict=True)
    ]


def _connect_channel(port: int, token: str, channel: str) -> socket.socket:
    connection = socket.create_connection(("127.0.0.1", port), timeout=30.0)
    connection.sendall(
        json.dumps({"channel": channel, "token": token}, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )
    connection.settimeout(None)
    return connection


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-port", type=int, required=True)
    parser.add_argument("--camera-port", type=int, required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    control = _connect_channel(args.control_port, args.token, "control")
    camera = _connect_channel(args.camera_port, args.token, "camera")
    try:
        Bridge(control, camera).run()
    finally:
        control.close()
        camera.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
