from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication
from ui.widgets.leaflet_map import LeafletMapWidget

MAP_WEB_ROOT = Path(__file__).resolve().parents[3] / "ui/web/map"


def test_map_page_uses_bundled_leaflet_without_runtime_network() -> None:
    html = (MAP_WEB_ROOT / "index.html").read_text(encoding="utf-8")

    assert "https://unpkg.com" not in html
    assert 'href="vendor/leaflet/leaflet.css"' in html
    assert 'src="vendor/leaflet/leaflet.js"' in html
    assert (MAP_WEB_ROOT / "vendor/leaflet/leaflet.css").is_file()
    assert (MAP_WEB_ROOT / "vendor/leaflet/leaflet.js").is_file()
    assert (MAP_WEB_ROOT / "vendor/leaflet/LICENSE").is_file()


def test_html_load_waits_for_javascript_bridge_before_flushing_updates() -> None:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QCoreApplication)
    widget = LeafletMapWidget(load_page=False)
    network = {"type": "FeatureCollection", "features": []}

    widget.set_network(network)
    widget._loaded(True)

    assert widget._ready is False
    assert widget._pending == {"setNetwork": network}
    widget.close()
