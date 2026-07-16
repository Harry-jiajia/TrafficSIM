import base64

from PySide6.QtCore import QBuffer, QByteArray, QIODeviceBase, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication
from ui.models import CameraFrame
from ui.widgets.camera_view import CameraDecoder


def _jpeg_base64() -> str:
    image = QImage(4, 3, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.darkCyan)
    encoded = QByteArray()
    buffer = QBuffer(encoded)
    assert buffer.open(QIODeviceBase.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "JPEG")  # type: ignore[call-overload]
    buffer.close()
    return base64.b64encode(bytes(encoded.data())).decode("ascii")


def test_camera_decoder_decodes_valid_jpeg_with_current_pyside_binding() -> None:
    app = QApplication.instance() or QApplication([])
    decoder = CameraDecoder()
    decoded = QSignalSpy(decoder.decoded)
    failed = QSignalSpy(decoder.failed)
    frame = CameraFrame(
        camera_id="main",
        carla_frame=42,
        simulation_time_ms=2100,
        width=4,
        height=3,
        data_base64=_jpeg_base64(),
    )

    decoder.submit(frame)

    assert decoder._pool.waitForDone(2000)  # noqa: SLF001 - verify real worker path
    app.processEvents()
    assert decoded.count() == 1
    assert failed.count() == 0
    image, carla_frame, simulation_time_ms = decoded.at(0)
    assert isinstance(image, QImage)
    assert (image.width(), image.height()) == (4, 3)
    assert carla_frame == 42
    assert simulation_time_ms == 2100
