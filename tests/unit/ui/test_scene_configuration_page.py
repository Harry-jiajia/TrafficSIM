from __future__ import annotations

from PySide6.QtWidgets import QApplication, QPushButton
from ui.models import MapSummary
from ui.views.scene_configuration_page import SceneConfigurationPage


def _application() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


def test_scene_configuration_only_lists_direct_sumo_packages() -> None:
    _application()
    page = SceneConfigurationPage()
    page.set_maps(
        (
            MapSummary(
                map_id="town04",
                kind="core_run",
                display_name="Town04",
                carla_map="Town04",
                carla_version="0.9.16",
                validated=True,
                network_schema_version="traffic-network/1.0",
            ),
            MapSummary(
                map_id="image2road",
                kind="sumo",
                display_name="image2road",
                validated=True,
                network_schema_version="sumo-net/display-1.0",
                manifest_available=False,
                sumo_config_file="image2road.sumocfg",
                sumo_step_ms=1000,
            ),
        )
    )

    assert page.map_combo.count() == 1
    assert page.map_combo.itemData(0) == "image2road"
    assert "Town04" not in page.map_combo.itemText(0)
    assert {button.text() for button in page.findChildren(QPushButton)} == {"创建实验"}

    page.close()
