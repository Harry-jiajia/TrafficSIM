"""CARLA runtime bridge for a Windows Python client hosted by Wine on macOS."""

from __future__ import annotations

import importlib
import io
import json
import os
import secrets
import socket
import struct
import subprocess
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, cast

from pydantic import JsonValue

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

_CAMERA_HEADER = struct.Struct("!4sQdIIII")
_CAMERA_MAGIC = b"TVRG"


def _wine_path(path: Path) -> str:
    absolute = path.expanduser().resolve()
    return "Z:" + str(absolute).replace("/", "\\")


def _required_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise RuntimeError(f"{label} does not exist: {resolved}")
    return resolved


@dataclass(frozen=True, slots=True)
class WineBridgeSettings:
    wine_executable: Path
    wine_prefix: Path
    python_executable: Path
    bridge_script: Path

    @classmethod
    def from_environment(cls, repository_root: Path) -> WineBridgeSettings:
        app = Path(
            os.getenv(
                "TRAFFICVERSE_CARLA_APP",
                str(Path.home() / "Applications" / "CARLA.app"),
            )
        ).expanduser()
        wine_executable = Path(
            os.getenv(
                "TRAFFICVERSE_CARLA_WINE_EXECUTABLE",
                str(app / "Contents/SharedSupport/wine/bin/wine"),
            )
        )
        wine_prefix = Path(
            os.getenv(
                "TRAFFICVERSE_CARLA_WINE_PREFIX",
                str(app / "Contents/SharedSupport/prefix"),
            )
        ).expanduser()
        python_executable = Path(
            os.getenv(
                "TRAFFICVERSE_CARLA_WINE_PYTHON",
                str(repository_root / "artifacts/runtime/wine-python312/python.exe"),
            )
        )
        if not wine_prefix.is_dir():
            raise RuntimeError(f"CARLA Wine prefix does not exist: {wine_prefix}")
        return cls(
            wine_executable=_required_file(wine_executable, "CARLA Wine executable"),
            wine_prefix=wine_prefix.resolve(),
            python_executable=_required_file(
                python_executable, "TrafficVerse Windows Python executable"
            ),
            bridge_script=_required_file(
                repository_root / "scripts/dev/wine_carla_bridge.py",
                "TrafficVerse Wine CARLA bridge",
            ),
        )


class WineBridgeTransport:
    """Local-only control RPC plus a dedicated bounded raw-camera stream."""

    def __init__(self, settings: WineBridgeSettings) -> None:
        self._settings = settings
        self._process: subprocess.Popen[bytes] | None = None
        self._control_socket: socket.socket | None = None
        self._control_file: BinaryIO | None = None
        self._camera_socket: socket.socket | None = None
        self._request_id = 0
        self._request_lock = threading.Lock()
        self._camera_thread: threading.Thread | None = None
        self._camera_callback: CameraCallback | None = None
        self._jpeg_quality = 75
        self._closed = False

    def start(self, *, timeout_s: float) -> None:
        control_listener = self._listener(timeout_s)
        camera_listener = self._listener(timeout_s)
        token = secrets.token_urlsafe(24)
        env = self._wine_environment()
        self._process = subprocess.Popen(
            [
                str(self._settings.wine_executable),
                _wine_path(self._settings.python_executable),
                _wine_path(self._settings.bridge_script),
                "--control-port",
                str(control_listener.getsockname()[1]),
                "--camera-port",
                str(camera_listener.getsockname()[1]),
                "--token",
                token,
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            self._control_socket = self._accept_channel(
                control_listener, token=token, channel="control"
            )
            self._camera_socket = self._accept_channel(
                camera_listener, token=token, channel="camera"
            )
        finally:
            control_listener.close()
            camera_listener.close()
        self._control_file = cast("BinaryIO", self._control_socket.makefile("rwb", buffering=0))
        self._camera_thread = threading.Thread(
            target=self._read_camera_frames,
            name="trafficverse-wine-camera",
            daemon=True,
        )
        self._camera_thread.start()

    @staticmethod
    def _listener(timeout_s: float) -> socket.socket:
        listener = socket.create_server(("127.0.0.1", 0), family=socket.AF_INET)
        listener.settimeout(timeout_s)
        return listener

    @staticmethod
    def _accept_channel(listener: socket.socket, *, token: str, channel: str) -> socket.socket:
        connection, address = listener.accept()
        if address[0] != "127.0.0.1":
            connection.close()
            raise RuntimeError("Wine CARLA bridge must connect through loopback")
        handshake = json.loads(_read_socket_line(connection).decode("utf-8"))
        if handshake != {"channel": channel, "token": token}:
            connection.close()
            raise RuntimeError(f"invalid Wine CARLA {channel} handshake")
        return connection

    def _wine_environment(self) -> dict[str, str]:
        wine_root = self._settings.wine_executable.parent.parent
        environment = os.environ.copy()
        environment.update(
            {
                "WINEPREFIX": str(self._settings.wine_prefix),
                "WINEDLLPATH": str(wine_root / "lib/wine"),
                "DYLD_FALLBACK_LIBRARY_PATH": f"{wine_root / 'lib'}:/opt/wine/lib",
                "WINEESYNC": "1",
                "WINEMSYNC": "1",
                "WINEDEBUG": "-all",
            }
        )
        return environment

    def request(self, operation: str, **payload: object) -> JsonValue:
        if self._closed or self._control_file is None:
            raise RuntimeError("Wine CARLA bridge is not connected")
        with self._request_lock:
            self._request_id += 1
            request_id = self._request_id
            message = json.dumps(
                {"id": request_id, "operation": operation, "payload": payload},
                separators=(",", ":"),
            ).encode("utf-8")
            self._control_file.write(message + b"\n")
            response = json.loads(self._control_file.readline().decode("utf-8"))
        if response.get("id") != request_id:
            raise RuntimeError("Wine CARLA bridge response ID mismatch")
        if not response.get("ok"):
            raise RuntimeError(str(response.get("error", "unknown Wine CARLA bridge error")))
        return cast("JsonValue", response.get("result"))

    def set_camera_callback(self, callback: CameraCallback, *, jpeg_quality: int) -> None:
        self._camera_callback = callback
        self._jpeg_quality = jpeg_quality

    def clear_camera_callback(self) -> None:
        self._camera_callback = None

    def _read_camera_frames(self) -> None:
        camera_socket = self._camera_socket
        if camera_socket is None:
            return
        while not self._closed:
            try:
                header = _recv_exact(camera_socket, _CAMERA_HEADER.size)
                magic, frame, timestamp, width, height, camera_id_size, raw_size = (
                    _CAMERA_HEADER.unpack(header)
                )
                if magic != _CAMERA_MAGIC:
                    raise RuntimeError("invalid Wine CARLA camera frame magic")
                camera_id = _recv_exact(camera_socket, camera_id_size).decode("ascii")
                raw = _recv_exact(camera_socket, raw_size)
                callback = self._camera_callback
                if callback is None:
                    continue
                callback(
                    RuntimeCameraFrame(
                        camera_id=camera_id,
                        carla_frame=frame,
                        simulation_time_ms=round(timestamp * 1000),
                        width=width,
                        height=height,
                        jpeg_bytes=_bgra_to_jpeg(raw, width, height, self._jpeg_quality),
                    )
                )
            except (EOFError, OSError):
                return

    def close(self) -> None:
        if self._closed:
            return
        try:
            if self._control_file is not None:
                self.request("shutdown")
        except (EOFError, OSError, RuntimeError):
            pass
        self._closed = True
        for resource in (self._control_file, self._control_socket, self._camera_socket):
            if resource is not None:
                resource.close()
        if self._process is not None:
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                self._process.wait(timeout=3)


class WineCarlaRuntime:
    """Typed CarlaRuntime implementation backed by a Windows client subprocess."""

    def __init__(self, transport: WineBridgeTransport) -> None:
        self._transport = transport
        self._started = False

    @classmethod
    def from_environment(cls, repository_root: Path) -> WineCarlaRuntime:
        return cls(WineBridgeTransport(WineBridgeSettings.from_environment(repository_root)))

    def connect(
        self, host: str, port: int, timeout_s: float, worker_threads: int
    ) -> RuntimeVersions:
        self._transport.start(timeout_s=timeout_s)
        self._started = True
        try:
            result = _mapping(
                self._transport.request(
                    "connect",
                    host=host,
                    port=port,
                    timeout_s=timeout_s,
                    worker_threads=worker_threads,
                )
            )
        except Exception:
            self._transport.close()
            self._started = False
            raise
        return RuntimeVersions(client=str(result["client"]), server=str(result["server"]))

    def load_world(self, map_name: str) -> None:
        self._transport.request("load_world", map_name=map_name)

    def get_world_settings(self) -> RuntimeWorldSettings:
        result = _mapping(self._transport.request("get_world_settings"))
        delta = result.get("fixed_delta_seconds")
        return RuntimeWorldSettings(
            synchronous_mode=bool(result["synchronous_mode"]),
            fixed_delta_seconds=None if delta is None else _float_value(delta),
        )

    def apply_world_settings(self, settings: RuntimeWorldSettings) -> None:
        self._transport.request(
            "apply_world_settings",
            synchronous_mode=settings.synchronous_mode,
            fixed_delta_seconds=settings.fixed_delta_seconds,
        )

    def set_weather(self, preset: str) -> None:
        self._transport.request("set_weather", preset=preset)

    def available_blueprints(self, pattern: str) -> tuple[str, ...]:
        return tuple(
            str(value)
            for value in _sequence(self._transport.request("blueprints", pattern=pattern))
        )

    def spawn_vehicles(
        self, requests: Sequence[RuntimeSpawnRequest]
    ) -> tuple[RuntimeSpawnResult, ...]:
        values = self._transport.request(
            "spawn_vehicles",
            requests=[_spawn_payload(request) for request in requests],
        )
        return tuple(
            RuntimeSpawnResult(
                vehicle_id=str(item["vehicle_id"]),
                actor_id=(None if item.get("actor_id") is None else _int_value(item["actor_id"])),
                error=None if item.get("error") is None else str(item["error"]),
            )
            for item in map(_mapping, _sequence(values))
        )

    def update_actors(
        self, updates: Sequence[tuple[int, RuntimeTransform]]
    ) -> tuple[RuntimeOperationResult, ...]:
        values = self._transport.request(
            "update_actors",
            updates=[
                {"actor_id": actor_id, "transform": _transform_payload(transform)}
                for actor_id, transform in updates
            ],
        )
        return _operation_results(values)

    def destroy_actors(self, actor_ids: Sequence[int]) -> tuple[RuntimeOperationResult, ...]:
        return _operation_results(
            self._transport.request("destroy_actors", actor_ids=list(actor_ids))
        )

    def existing_actor_ids(self, actor_ids: Sequence[int]) -> frozenset[int]:
        return frozenset(
            _int_value(value)
            for value in _sequence(
                self._transport.request("existing_actor_ids", actor_ids=list(actor_ids))
            )
        )

    def freeze_traffic_lights(self, frozen: bool) -> None:
        self._transport.request("freeze_traffic_lights", frozen=frozen)

    def traffic_lights(self) -> tuple[RuntimeTrafficLight, ...]:
        return tuple(
            RuntimeTrafficLight(
                actor_id=_int_value(item["actor_id"]),
                opendrive_id=str(item["opendrive_id"]),
                frozen=bool(item["frozen"]),
            )
            for item in map(_mapping, _sequence(self._transport.request("traffic_lights")))
        )

    def update_traffic_lights(
        self, updates: Sequence[tuple[int, TrafficLightColor]]
    ) -> tuple[RuntimeOperationResult, ...]:
        return _operation_results(
            self._transport.request(
                "update_traffic_lights",
                updates=[
                    {"actor_id": actor_id, "color": color.value} for actor_id, color in updates
                ],
            )
        )

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
        self._transport.set_camera_callback(callback, jpeg_quality=jpeg_quality)
        self._transport.request(
            "start_camera",
            mode=mode,
            target_actor_id=target_actor_id,
            width=width,
            height=height,
            fps=fps,
        )

    def stop_camera(self) -> None:
        if not self._started:
            return
        self._transport.clear_camera_callback()
        self._transport.request("stop_camera")

    def tick(self, timeout_s: float) -> int:
        return _int_value(self._transport.request("tick", timeout_s=timeout_s))

    def actor_count(self) -> int:
        return _int_value(self._transport.request("actor_count"))

    def disconnect(self) -> None:
        if not self._started:
            return
        try:
            self._transport.request("disconnect")
        finally:
            self._transport.close()
            self._started = False


def _read_socket_line(connection: socket.socket) -> bytes:
    value = bytearray()
    while len(value) <= 4096:
        byte = connection.recv(1)
        if not byte:
            raise EOFError("Wine CARLA bridge closed during handshake")
        if byte == b"\n":
            return bytes(value)
        value.extend(byte)
    raise RuntimeError("Wine CARLA bridge handshake exceeded 4096 bytes")


def _recv_exact(connection: socket.socket, size: int) -> bytes:
    value = bytearray()
    while len(value) < size:
        chunk = connection.recv(size - len(value))
        if not chunk:
            raise EOFError("Wine CARLA camera stream closed")
        value.extend(chunk)
    return bytes(value)


def _bgra_to_jpeg(raw: bytes, width: int, height: int, quality: int) -> bytes:
    image_module = importlib.import_module("PIL.Image")
    image = image_module.frombytes("RGBA", (width, height), raw, "raw", "BGRA")
    stream = io.BytesIO()
    image.convert("RGB").save(stream, format="JPEG", quality=quality)
    return stream.getvalue()


def _mapping(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise RuntimeError("Wine CARLA bridge returned a non-object result")
    return value


def _sequence(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise RuntimeError("Wine CARLA bridge returned a non-array result")
    return value


def _int_value(value: JsonValue) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise RuntimeError("Wine CARLA bridge returned a non-integer result")
    return int(value)


def _float_value(value: JsonValue) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise RuntimeError("Wine CARLA bridge returned a non-number result")
    return float(value)


def _transform_payload(transform: RuntimeTransform) -> dict[str, float]:
    return {
        "x": transform.x,
        "y": transform.y,
        "z": transform.z,
        "heading_rad": transform.heading_rad,
    }


def _spawn_payload(request: RuntimeSpawnRequest) -> dict[str, object]:
    return {
        "vehicle_id": request.vehicle_id,
        "blueprint_id": request.blueprint_id,
        "transform": _transform_payload(request.transform),
    }


def _operation_results(value: JsonValue) -> tuple[RuntimeOperationResult, ...]:
    return tuple(
        RuntimeOperationResult(
            actor_id=_int_value(item["actor_id"]),
            error=None if item.get("error") is None else str(item["error"]),
        )
        for item in map(_mapping, _sequence(value))
    )
