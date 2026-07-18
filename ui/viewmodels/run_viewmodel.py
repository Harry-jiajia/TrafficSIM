"""Run-page state and commands, independent from concrete widgets."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QObject, QTimer, Signal

from ui.api_client import RealtimeClient, RestApiClient
from ui.models import (
    ControlAvailability,
    Envelope,
    ExperimentStatus,
    ExperimentView,
    MapImportJob,
    MapManifest,
    MapSummary,
    ReadinessResponse,
    WorldState,
)


class RunViewModel(QObject):
    map_catalog_changed = Signal(object)
    map_manifest_changed = Signal(str, object)
    asset_network_changed = Signal(str, object)
    selected_map_changed = Signal(str)
    network_changed = Signal(object)
    vehicles_changed = Signal(object)
    traffic_lights_changed = Signal(object)
    component_health_changed = Signal(object)
    experiment_status_changed = Signal(str)
    simulation_time_changed = Signal(int)
    control_availability_changed = Signal(object)
    connection_changed = Signal(str)
    notification = Signal(str, str)

    def __init__(
        self,
        rest: RestApiClient,
        realtime: RealtimeClient,
        scenario_id: UUID,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._rest = rest
        self._realtime = realtime
        self._scenario_id = scenario_id
        self._maps: tuple[MapSummary, ...] = ()
        self._selected_map_id: str | None = None
        self._import_job_id: UUID | None = None
        self._experiment_id: UUID | None = None
        self._status: ExperimentStatus | None = None
        self._world: WorldState | None = None
        self._start_after_prepare = False
        self._import_timer = QTimer(self)
        self._import_timer.setInterval(500)
        self._import_timer.timeout.connect(self._poll_import)
        rest.request_succeeded.connect(self.handle_rest_success)
        rest.request_failed.connect(self.handle_rest_failure)
        realtime.connection_changed.connect(self.connection_changed)
        realtime.envelope_received.connect(self.handle_envelope)
        realtime.protocol_error.connect(
            lambda message: self.notification.emit("error", f"实时协议错误：{message}")
        )

    @property
    def experiment_id(self) -> UUID | None:
        return self._experiment_id

    @property
    def status(self) -> ExperimentStatus | None:
        return self._status

    def initialize(self) -> None:
        # Readiness describes a prepared experiment and is expected to fail before one exists.
        # At UI startup only probe whether the API control plane is reachable.
        self._rest.check_health()
        self._rest.list_maps()
        self._emit_controls()

    def select_map(self, map_id: str) -> None:
        if map_id not in {item.map_id for item in self._maps}:
            self.notification.emit("error", "所选地图不在已验证地图列表中。")
            return
        self._selected_map_id = map_id
        self.selected_map_changed.emit(map_id)
        self._rest.get_map_network(map_id)

    def preview_map_asset(self, map_id: str) -> None:
        if map_id not in {item.map_id for item in self._maps}:
            self.notification.emit("error", "所选地图资产不在目录中。")
            return
        self._rest.get_asset_map_network(map_id)

    def import_map(self, path: Path) -> None:
        if path.suffix.lower() != ".xodr":
            self.notification.emit("error", "请选择 .xodr 格式的 OpenDRIVE 地图。")
            return
        self.notification.emit("info", "正在上传并校验地图……")
        self._rest.import_map(path)

    def create_experiment(self) -> None:
        if self._selected_map_id is None:
            self.notification.emit("error", "请先选择一份已验证地图。")
            return
        self._rest.create_experiment(self._scenario_id, self._selected_map_id)

    def start(self) -> None:
        if self._status is ExperimentStatus.CREATED:
            self._start_after_prepare = True
            self._send("experiment.prepare", {})
        elif self._status is ExperimentStatus.READY:
            self._send("experiment.start", {})

    def pause(self) -> None:
        self._send("experiment.pause", {})

    def resume(self) -> None:
        self._send("experiment.resume", {})

    def stop(self) -> None:
        self._send("experiment.stop", {"reason": "USER_REQUEST"})

    def set_speed(self, multiplier: float) -> None:
        self._send("experiment.speed.set", {"multiplier": multiplier})

    def control_vehicle(
        self,
        vehicle_id: str,
        *,
        desired_speed_mps: float | None = None,
        lane_change: str = "NONE",
        stop_requested: bool = False,
    ) -> None:
        if not vehicle_id:
            self.notification.emit("error", "请输入车辆 ID。")
            return
        payload: dict[str, object] = {
            "vehicle_id": vehicle_id,
            "lane_change": lane_change,
            "stop_requested": stop_requested,
        }
        if desired_speed_mps is not None:
            payload["desired_speed_mps"] = desired_speed_mps
        self._send("vehicle.control", payload)

    def handle_rest_success(self, operation: str, payload: object) -> None:
        if operation == "health":
            self.connection_changed.emit("API_CONNECTED")
        elif operation == "ready":
            readiness = ReadinessResponse.model_validate(payload)
            if not readiness.ready:
                self.notification.emit("warning", "后端尚未就绪，请检查组件状态。")
            self.component_health_changed.emit(readiness.components)
        elif operation == "maps.list":
            self._maps = tuple(MapSummary.model_validate(item) for item in _items(payload))
            self.map_catalog_changed.emit(self._maps)
            for item in self._maps:
                self._rest.get_map_manifest(item.map_id)
            if self._maps and self._selected_map_id is None:
                self.select_map(self._maps[0].map_id)
        elif operation.startswith("map.manifest:"):
            map_id = operation.removeprefix("map.manifest:")
            manifest = MapManifest.model_validate(payload)
            if manifest.map_id != map_id:
                raise ValueError("map manifest id does not match the requested asset")
            self.map_manifest_changed.emit(map_id, manifest)
        elif operation.startswith("asset.map.network:"):
            map_id = operation.removeprefix("asset.map.network:")
            self.asset_network_changed.emit(map_id, payload)
        elif operation.startswith("map.network:"):
            self.network_changed.emit(payload)
        elif operation == "map.import.submit" or operation.startswith("map.import:"):
            self._handle_import_job(MapImportJob.model_validate(payload))
        elif operation == "experiment.create" or operation.startswith("experiment.get:"):
            self._set_experiment(ExperimentView.model_validate(payload))

    def handle_rest_failure(self, operation: str, message: str) -> None:
        if operation.startswith("map.import"):
            self._import_timer.stop()
        self.notification.emit("error", f"操作失败：{message}")

    def handle_envelope(self, payload: object) -> None:
        try:
            envelope = Envelope.model_validate(payload)
            if self._world is None:
                return
            update = self._world.apply(envelope)
            self.simulation_time_changed.emit(self._world.simulation_time_ms)
            if update.sequence_gap is not None:
                previous, current = update.sequence_gap
                self.notification.emit(
                    "warning", f"实时数据从序号 {previous} 跳到 {current}，正在恢复完整快照。"
                )
                self._realtime.request_snapshot()
            if update.vehicles_changed:
                self.vehicles_changed.emit(tuple(self._world.vehicles.values()))
            if update.traffic_lights_changed:
                self.traffic_lights_changed.emit(tuple(self._world.traffic_lights.values()))
            if update.health_changed:
                self.component_health_changed.emit(tuple(self._world.components.values()))
            if update.status_changed and self._world.status is not None:
                self._set_status(self._world.status)
            if envelope.type == "command.rejected":
                message = (
                    envelope.payload.get("message") if isinstance(envelope.payload, dict) else None
                )
                self.notification.emit("error", str(message or "命令被后端拒绝。"))
            elif envelope.type == "error":
                self.notification.emit("error", "后端报告实时协议错误。")
        except (ValueError, TypeError) as error:
            self.notification.emit("error", f"无法处理实时消息：{error}")

    def _set_experiment(self, view: ExperimentView) -> None:
        self._experiment_id = view.experiment_id
        self._world = WorldState(view.experiment_id, simulation_time_ms=view.simulation_time_ms)
        self._set_status(view.status)
        self._realtime.connect_to_experiment(view.experiment_id)

    def _set_status(self, status: ExperimentStatus) -> None:
        self._status = status
        self.experiment_status_changed.emit(status.value)
        self._emit_controls()
        if status is ExperimentStatus.READY and self._start_after_prepare:
            self._start_after_prepare = False
            self._send("experiment.start", {})

    def _send(self, command: str, payload: dict[str, object]) -> None:
        if self._experiment_id is None:
            self.notification.emit("error", "请先创建实验。")
            return
        try:
            self._realtime.send_command(command, payload)
        except RuntimeError as error:
            self.notification.emit("error", f"命令发送失败：{error}")

    def _handle_import_job(self, job: MapImportJob) -> None:
        self._import_job_id = job.job_id
        if job.status in {"PENDING", "RUNNING"}:
            self._import_timer.start()
            return
        self._import_timer.stop()
        if job.status == "FAILED":
            detail = "; ".join(job.errors) or "地图校验失败"
            self.notification.emit("error", detail)
            return
        self.notification.emit("success", "地图编译和校验已完成。")
        self._rest.list_maps()

    def _poll_import(self) -> None:
        if self._import_job_id is not None:
            self._rest.get_import_job(self._import_job_id)

    def _emit_controls(self) -> None:
        self.control_availability_changed.emit(ControlAvailability.for_status(self._status))


def _items(payload: object) -> list[object]:
    if not isinstance(payload, list):
        raise ValueError("REST response must be an array")
    return payload
