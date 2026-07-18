from __future__ import annotations

from PySide6.QtWidgets import QApplication, QLabel
from ui.views.navigation import NavigationRail


def _application() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


def test_brand_logo_renders_the_complete_svg_canvas() -> None:
    _application()
    navigation = NavigationRail()
    label = navigation.findChild(QLabel, "brandLogo")

    assert label is not None
    pixmap = label.pixmap()
    assert pixmap is not None
    image = pixmap.toImage()
    corners = (
        (0, 0),
        (image.width() - 1, 0),
        (0, image.height() - 1),
        (image.width() - 1, image.height() - 1),
    )
    assert all(image.pixelColor(x, y).alpha() == 255 for x, y in corners)

    navigation.close()
