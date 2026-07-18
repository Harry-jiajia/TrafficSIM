from __future__ import annotations

from pathlib import Path

from ui.widgets.leaflet_map import LeafletMapWidget
from ui.widgets.maplibre_deck_map import MapLibreDeckMapWidget

MAP_WEB_ROOT = Path(__file__).resolve().parents[3] / "ui/web/map"


def test_leaflet_assets_are_retained_but_not_loaded_by_the_active_page() -> None:
    html = (MAP_WEB_ROOT / "index.html").read_text(encoding="utf-8")

    assert "vendor/leaflet" not in html
    assert (MAP_WEB_ROOT / "vendor/leaflet/leaflet.css").is_file()
    assert (MAP_WEB_ROOT / "vendor/leaflet/leaflet.js").is_file()
    assert (MAP_WEB_ROOT / "vendor/leaflet/LICENSE").is_file()


def test_leaflet_widget_name_is_a_compatibility_alias() -> None:
    assert LeafletMapWidget is MapLibreDeckMapWidget
