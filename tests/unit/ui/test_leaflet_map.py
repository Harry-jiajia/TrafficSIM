from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication
from ui.widgets.leaflet_map import LeafletMapWidget


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
