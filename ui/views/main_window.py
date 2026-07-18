"""Core Run desktop window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ui.models import ControlAvailability, MapSummary
from ui.viewmodels import RunViewModel
from ui.widgets import CarlaNativeWindowHost, MapLibreDeckMapWidget


class MainWindow(QMainWindow):
    def __init__(self, viewmodel: RunViewModel, *, load_web_map: bool = True) -> None:
        super().__init__()
        self._viewmodel = viewmodel
        self._load_web_map = load_web_map
        self.setWindowTitle("TrafficVerse · 全局二维 + 局部三维")
        self.resize(1500, 900)
        self.setMinimumSize(1100, 700)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        layout.addLayout(self._header())
        layout.addWidget(self._notice)
        layout.addWidget(self._workspace(), 1)
        layout.addWidget(self._hud())
        layout.addWidget(self._controls())
        self.setCentralWidget(root)
        self._connect_viewmodel()
        self._apply_theme()

    def _header(self) -> QHBoxLayout:
        title = QLabel("TrafficVerse")
        title.setObjectName("title")
        subtitle = QLabel("Town04 Core Run · SUMO 真值 + 本机 CARLA 原生窗口")
        subtitle.setObjectName("subtitle")
        title_stack = QVBoxLayout()
        title_stack.setSpacing(1)
        title_stack.addWidget(title)
        title_stack.addWidget(subtitle)

        self._map_combo = QComboBox()
        self._map_combo.setMinimumWidth(310)
        self._map_combo.currentIndexChanged.connect(self._select_map)
        self._import_button = QPushButton("导入 .xodr")
        self._import_button.clicked.connect(self._choose_map)
        self._connection = QLabel("API 连接中")
        self._connection.setObjectName("badge")
        self._notice = QLabel("")
        self._notice.setVisible(False)
        self._notice.setWordWrap(True)
        self._notice.setObjectName("notice")

        row = QHBoxLayout()
        row.addLayout(title_stack)
        row.addStretch(1)
        row.addWidget(QLabel("地图"))
        row.addWidget(self._map_combo)
        row.addWidget(self._import_button)
        row.addWidget(self._connection)
        return row

    def _workspace(self) -> QSplitter:
        self._map = MapLibreDeckMapWidget(load_page=self._load_web_map)
        self._map.vehicle_selected.connect(self._set_vehicle_id)
        self._carla_window = CarlaNativeWindowHost()
        map_panel = self._panel("全局二维交通", self._map)
        carla_panel = self._panel("ROI 局部三维 · CARLA 原生窗口", self._carla_window)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(map_panel)
        splitter.addWidget(carla_panel)
        splitter.setSizes([850, 600])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        return splitter

    def _hud(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QGridLayout(frame)
        self._experiment_status = self._metric("实验状态", "未创建")
        self._simulation_time = self._metric("仿真时间", "0.00 s")
        self._vehicle_count = self._metric("全局车辆", "0")
        self._carla_status = self._metric("CARLA", "等待")
        for column, widget in enumerate(
            (
                self._experiment_status,
                self._simulation_time,
                self._vehicle_count,
                self._carla_status,
            )
        ):
            layout.addWidget(widget, 0, column)
        return frame

    def _controls(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QHBoxLayout(frame)
        self._create = QPushButton("创建实验")
        self._start = QPushButton("开始")
        self._pause = QPushButton("暂停")
        self._resume = QPushButton("恢复")
        self._stop = QPushButton("停止")
        self._create.clicked.connect(self._viewmodel.create_experiment)
        self._start.clicked.connect(self._viewmodel.start)
        self._pause.clicked.connect(self._viewmodel.pause)
        self._resume.clicked.connect(self._viewmodel.resume)
        self._stop.clicked.connect(self._viewmodel.stop)
        for button in (self._create, self._start, self._pause, self._resume, self._stop):
            layout.addWidget(button)

        layout.addSpacing(16)
        layout.addWidget(QLabel("倍率"))
        self._speed = QComboBox()
        self._speed.addItems(["0.5×", "1×", "2×"])
        self._speed.setCurrentIndex(1)
        self._speed.currentIndexChanged.connect(self._set_speed)
        layout.addWidget(self._speed)
        layout.addStretch(1)

        self._vehicle_id = QLineEdit()
        self._vehicle_id.setPlaceholderText("车辆 ID（可在地图点击）")
        self._vehicle_id.setMinimumWidth(190)
        self._desired_speed = QDoubleSpinBox()
        self._desired_speed.setRange(0.0, 60.0)
        self._desired_speed.setValue(8.0)
        self._desired_speed.setSuffix(" m/s")
        self._apply_speed = QPushButton("设置车速")
        self._left = QPushButton("左换道")
        self._right = QPushButton("右换道")
        self._vehicle_stop = QPushButton("单车停车")
        self._apply_speed.clicked.connect(self._control_speed)
        self._left.clicked.connect(lambda: self._control_lane("LEFT"))
        self._right.clicked.connect(lambda: self._control_lane("RIGHT"))
        self._vehicle_stop.clicked.connect(self._control_stop)
        layout.addWidget(self._vehicle_id)
        layout.addWidget(self._desired_speed)
        layout.addWidget(self._apply_speed)
        layout.addWidget(self._left)
        layout.addWidget(self._right)
        layout.addWidget(self._vehicle_stop)
        return frame

    @staticmethod
    def _panel(title: str, content: QWidget) -> QFrame:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        label = QLabel(title)
        label.setObjectName("panelTitle")
        layout.addWidget(label)
        layout.addWidget(content, 1)
        return frame

    @staticmethod
    def _metric(label: str, value: str) -> QWidget:
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 4, 12, 4)
        name = QLabel(label)
        name.setObjectName("metricName")
        number = QLabel(value)
        number.setObjectName("metricValue")
        layout.addWidget(name)
        layout.addWidget(number)
        return widget

    def _connect_viewmodel(self) -> None:
        vm = self._viewmodel
        vm.map_catalog_changed.connect(self._set_maps)
        vm.network_changed.connect(self._map.set_network)
        vm.vehicles_changed.connect(self._set_vehicles)
        vm.traffic_lights_changed.connect(self._map.set_traffic_lights)
        vm.component_health_changed.connect(self._set_health)
        vm.experiment_status_changed.connect(self._set_status)
        vm.simulation_time_changed.connect(self._set_time)
        vm.control_availability_changed.connect(self._set_controls)
        vm.connection_changed.connect(self._set_connection)
        vm.notification.connect(self._show_notice)

    @Slot(object)
    def _set_maps(self, maps: object) -> None:
        values = maps if isinstance(maps, tuple) else ()
        self._map_combo.blockSignals(True)
        self._map_combo.clear()
        for item in values:
            if isinstance(item, MapSummary):
                self._map_combo.addItem(f"{item.carla_map} · {item.map_id}", item.map_id)
        self._map_combo.blockSignals(False)
        if self._map_combo.count():
            self._map_combo.setCurrentIndex(0)

    @Slot(object)
    def _set_vehicles(self, vehicles: object) -> None:
        self._map.set_vehicles(vehicles)
        count = len(vehicles) if isinstance(vehicles, tuple) else 0
        self._metric_value(self._vehicle_count).setText(str(count))

    @Slot(object)
    def _set_health(self, components: object) -> None:
        values = components if isinstance(components, tuple) else ()
        carla = next(
            (item for item in values if getattr(item, "component", "") == "carla"),
            None,
        )
        status = getattr(carla, "status", "UNKNOWN")
        self._metric_value(self._carla_status).setText(str(status))
        if carla is not None and str(status) not in {"HEALTHY", "ComponentStatus.HEALTHY"}:
            message = getattr(carla, "message", None) or "本机 CARLA 当前不可用"
            self._carla_window.show_unavailable(str(message))

    @Slot(str)
    def _set_status(self, status: str) -> None:
        self._metric_value(self._experiment_status).setText(status)

    @Slot(int)
    def _set_time(self, simulation_time_ms: int) -> None:
        self._metric_value(self._simulation_time).setText(f"{simulation_time_ms / 1000:.2f} s")

    @Slot(object)
    def _set_controls(self, availability: object) -> None:
        if not isinstance(availability, ControlAvailability):
            return
        self._create.setEnabled(availability.can_create)
        self._start.setEnabled(availability.can_start)
        self._pause.setEnabled(availability.can_pause)
        self._resume.setEnabled(availability.can_resume)
        self._stop.setEnabled(availability.can_stop)
        for widget in (self._apply_speed, self._left, self._right, self._vehicle_stop):
            widget.setEnabled(availability.can_control_vehicle)

    @Slot(str)
    def _set_connection(self, state: str) -> None:
        labels = {
            "API_CONNECTED": "API 已连接",
            "CONNECTED": "实时已连接",
            "CONNECTING": "实时连接中",
            "RECONNECTING": "实时重连中",
            "DISCONNECTED": "实时已断开",
        }
        self._connection.setText(labels.get(state, state))

    @Slot(str, str)
    def _show_notice(self, level: str, message: str) -> None:
        self._notice.setProperty("level", level)
        self._notice.setText(message)
        self._notice.setVisible(True)
        self._notice.style().unpolish(self._notice)
        self._notice.style().polish(self._notice)

    @Slot(int)
    def _select_map(self, index: int) -> None:
        map_id = self._map_combo.itemData(index)
        if isinstance(map_id, str):
            self._viewmodel.select_map(map_id)

    def _choose_map(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入 OpenDRIVE 地图",
            str(Path.home()),
            "OpenDRIVE (*.xodr)",
        )
        if path:
            self._viewmodel.import_map(Path(path))

    def _set_speed(self, index: int) -> None:
        self._viewmodel.set_speed((0.5, 1.0, 2.0)[index])

    def _control_speed(self) -> None:
        self._viewmodel.control_vehicle(
            self._vehicle_id.text().strip(), desired_speed_mps=self._desired_speed.value()
        )

    def _control_lane(self, direction: str) -> None:
        self._viewmodel.control_vehicle(self._vehicle_id.text().strip(), lane_change=direction)

    def _control_stop(self) -> None:
        self._viewmodel.control_vehicle(self._vehicle_id.text().strip(), stop_requested=True)

    @Slot(str)
    def _set_vehicle_id(self, vehicle_id: str) -> None:
        self._vehicle_id.setText(vehicle_id)

    @staticmethod
    def _metric_value(widget: QWidget) -> QLabel:
        values = widget.findChildren(QLabel, "metricValue")
        return values[0]

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background:#090e15; color:#dbe6f1; font-size:13px; }
            QLabel#title { font-size:25px; font-weight:700; color:#f5f9ff; }
            QLabel#subtitle, QLabel#metricName { color:#8193a8; }
            QLabel#badge { background:#142234; color:#64d7ff; padding:7px 11px; border-radius:9px; }
            QLabel#notice {
              background:#162334; padding:9px 12px; border-radius:7px; color:#b9d7ed;
            }
            QLabel#notice[level="error"] { background:#391c25; color:#ff9baa; }
            QLabel#notice[level="success"] { background:#123326; color:#77e6ad; }
            QFrame#panel { background:#101722; border:1px solid #1e2a3a; border-radius:10px; }
            QLabel#panelTitle { font-size:15px; font-weight:600; color:#eef5fc; }
            QLabel#metricValue { font-size:20px; font-weight:650; color:#f3f8ff; }
            QPushButton, QComboBox, QLineEdit, QDoubleSpinBox {
              background:#162233; border:1px solid #2a3a50; border-radius:7px; padding:7px 10px;
            }
            QPushButton:hover { border-color:#3bbff2; }
            QPushButton:disabled { color:#536174; background:#111923; border-color:#1b2634; }
            QPushButton#primary { background:#087cab; color:white; }
            QSplitter::handle { background:#090e15; width:8px; }
            """
        )
