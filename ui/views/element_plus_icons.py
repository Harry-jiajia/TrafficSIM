"""Render vendored Element Plus SVG assets using the active Qt palette."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICON_SIZE = QSize(18, 18)
_DEVICE_PIXEL_RATIO = 2


def render_element_plus_icon(path: Path, color: QColor) -> QIcon:
    """Render an Element Plus currentColor SVG for a themed navigation button."""
    source = path.read_text(encoding="utf-8").replace("currentColor", color.name())
    physical_size = ICON_SIZE * _DEVICE_PIXEL_RATIO
    pixmap = QPixmap(physical_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer = QSvgRenderer(QByteArray(source.encode("utf-8")))
    renderer.render(painter, QRectF(0, 0, physical_size.width(), physical_size.height()))
    painter.end()
    pixmap.setDevicePixelRatio(_DEVICE_PIXEL_RATIO)
    return QIcon(pixmap)


def render_svg_pixmap(path: Path, logical_size: QSize) -> QPixmap:
    """Render a color SVG to a transparent high-DPI pixmap."""

    physical_size = logical_size * _DEVICE_PIXEL_RATIO
    pixmap = QPixmap(physical_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(str(path))
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, physical_size.width(), physical_size.height()))
    painter.end()
    pixmap.setDevicePixelRatio(_DEVICE_PIXEL_RATIO)
    return pixmap
