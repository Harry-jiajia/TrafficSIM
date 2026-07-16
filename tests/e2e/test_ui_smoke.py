from __future__ import annotations

from uuid import UUID

import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtWidgets import QApplication
from ui.viewmodels import RunViewModel
from ui.views import MainWindow


class _Rest(QObject):
    request_succeeded = Signal(str, object)
    request_failed = Signal(str, str)


class _Realtime(QObject):
    connection_changed = Signal(str)
    envelope_received = Signal(object)
    protocol_error = Signal(str)


@pytest.mark.e2e
def test_core_run_window_constructs_and_closes_without_backend_or_carla() -> None:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QCoreApplication)
    viewmodel = RunViewModel(
        _Rest(),  # type: ignore[arg-type]
        _Realtime(),  # type: ignore[arg-type]
        UUID("00000000-0000-0000-0000-000000000042"),
    )

    window = MainWindow(viewmodel, load_web_map=False)

    assert window.windowTitle().startswith("TrafficVerse")
    assert window.minimumWidth() >= 1100
    window.close()
