"""Latest-only background JPEG decoder and camera display."""

from __future__ import annotations

import base64
import binascii
import threading

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.models import CameraFrame


class _DecodeTask(QRunnable):
    def __init__(self, decoder: CameraDecoder) -> None:
        super().__init__()
        self._decoder = decoder

    def run(self) -> None:
        self._decoder._drain()  # noqa: SLF001 - private worker pair


class CameraDecoder(QObject):
    decoded = Signal(object, int, int)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._latest: CameraFrame | None = None
        self._running = False
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)

    def submit(self, frame: CameraFrame) -> None:
        with self._lock:
            self._latest = frame
            if self._running:
                return
            self._running = True
        self._pool.start(_DecodeTask(self))

    def _drain(self) -> None:
        while True:
            with self._lock:
                frame = self._latest
                self._latest = None
                if frame is None:
                    self._running = False
                    return
            try:
                raw = base64.b64decode(frame.data_base64, validate=True)
                image = QImage.fromData(raw, b"JPEG")
                if image.isNull():
                    raise ValueError("JPEG 数据无效")
                self.decoded.emit(image, frame.carla_frame, frame.simulation_time_ms)
            except (ValueError, binascii.Error) as error:
                self.failed.emit(str(error))


class CameraView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image: QImage | None = None
        self._last_carla_frame = -1
        self._label = QLabel("CARLA 三维画面尚未连接")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(QSize(480, 270))
        self._label.setStyleSheet("background:#101722;color:#8ea0b8;border-radius:8px;")
        self._metadata = QLabel("等待 camera.frame")
        self._metadata.setStyleSheet("color:#8ea0b8;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label, 1)
        layout.addWidget(self._metadata)
        self._decoder = CameraDecoder(self)
        self._decoder.decoded.connect(self._show_image)
        self._decoder.failed.connect(lambda message: self.show_degraded(f"相机帧错误：{message}"))

    @Slot(object)
    def submit_frame(self, frame: object) -> None:
        if isinstance(frame, CameraFrame) and frame.carla_frame > self._last_carla_frame:
            self._decoder.submit(frame)

    @Slot(str)
    def show_degraded(self, reason: str) -> None:
        self._image = None
        self._label.setPixmap(QPixmap())
        self._label.setText(f"三维视图已降级\n{reason}")
        self._metadata.setText("二维交通仿真可继续运行")

    @Slot(object, int, int)
    def _show_image(self, image: object, carla_frame: int, simulation_time_ms: int) -> None:
        if not isinstance(image, QImage) or carla_frame <= self._last_carla_frame:
            return
        self._last_carla_frame = carla_frame
        self._image = image
        self._metadata.setText(
            f"CARLA frame {carla_frame} · 仿真 {simulation_time_ms / 1000:.2f} s"
        )
        self._render()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._render()

    def _render(self) -> None:
        if self._image is None:
            return
        pixmap = QPixmap.fromImage(self._image).scaled(
            self._label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(pixmap)
