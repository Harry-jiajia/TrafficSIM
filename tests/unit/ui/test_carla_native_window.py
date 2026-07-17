from __future__ import annotations

import pytest
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QApplication, QWidget
from ui.widgets import CarlaNativeWindowHost


def _application() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


def test_missing_window_id_reports_unavailable_without_rgb_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRAFFICVERSE_CARLA_WINDOW_ID", raising=False)
    _application()
    host = CarlaNativeWindowHost(auto_attach=False)

    host.attach_from_environment()

    assert not host.attached


def test_attach_and_detach_manage_only_qt_wrapper() -> None:
    _application()
    foreign_window = QWindow()

    def window_factory(window_id: int) -> QWindow:
        assert window_id == 42
        return foreign_window

    def container_factory(window: QWindow, parent: QWidget) -> QWidget:
        assert window is foreign_window
        return QWidget(parent)

    host = CarlaNativeWindowHost(
        auto_attach=False,
        window_factory=window_factory,
        container_factory=container_factory,
    )

    host.attach(42)
    assert host.attached

    host.detach()
    assert not host.attached


def test_unavailable_health_detaches_stale_window() -> None:
    _application()
    host = CarlaNativeWindowHost(
        auto_attach=False,
        window_factory=lambda _window_id: QWindow(),
        container_factory=lambda _window, parent: QWidget(parent),
    )
    host.attach(42)

    host.show_unavailable("CARLA RPC disconnected")

    assert not host.attached
