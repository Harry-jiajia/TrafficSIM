from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from ui.views.theme import (
    ThemeMode,
    configure_application_font,
    load_icon_colors,
    load_stylesheet,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
UI_ROOT = REPOSITORY_ROOT / "ui"


def _application() -> QApplication:
    existing = QApplication.instance()
    return existing if isinstance(existing, QApplication) else QApplication([])


def test_qt_theme_styles_are_external_and_cover_dark_and_light_modes() -> None:
    _application()
    dark = load_stylesheet(ThemeMode.DARK)
    light = load_stylesheet(ThemeMode.LIGHT)

    assert dark != light
    assert "QMainWindow" in dark
    assert "QMainWindow" in light
    assert "font-family" in dark
    assert "font-family" in light
    assert 'QPushButton[role="navigation"]' in dark
    assert 'QPushButton[role="navigation"]' in light
    assert "font-size: 15px" in dark
    assert "font-size: 15px" in light
    for stylesheet in (dark, light):
        assert "#409eff" in stylesheet.lower()
        assert "#67c23a" in stylesheet.lower()
        assert "#e6a23c" in stylesheet.lower()
        assert "#f56c6c" in stylesheet.lower()


def test_qt_theme_resolves_font_declarations_to_installed_families() -> None:
    _application()

    for theme in ThemeMode:
        stylesheet = load_stylesheet(theme)
        font_families = re.findall(r'font-family:\s*"([^"]+)"\s*;', stylesheet)

        assert len(set(font_families)) == 2
        assert all(QFontDatabase.hasFamily(family) for family in font_families)
        assert "Microsoft YaHei" not in stylesheet
        assert "__TRAFFICVERSE_" not in stylesheet


def test_qt_application_uses_the_resolved_interface_font() -> None:
    app = _application()

    configure_application_font()

    dark = load_stylesheet(ThemeMode.DARK)
    interface_font = re.search(r'font-family:\s*"([^"]+)"\s*;', dark)
    assert interface_font is not None
    assert app.font().family() == interface_font.group(1)


def test_element_plus_navigation_icons_are_local_svg_assets() -> None:
    icon_root = UI_ROOT / "assets/icons/element-plus"
    expected = {
        "monitor.svg",
        "set-up.svg",
        "data-board.svg",
        "trend-charts.svg",
        "box.svg",
        "setting.svg",
    }

    assert {path.name for path in icon_root.glob("*.svg")} == expected
    assert all(
        "currentColor" in path.read_text(encoding="utf-8") for path in icon_root.glob("*.svg")
    )
    notice = (icon_root / "README.md").read_text(encoding="utf-8")
    assert "@element-plus/icons-svg" in notice
    assert "MIT" in notice

    assert load_icon_colors(ThemeMode.DARK) == {"normal": "#cfd3dc", "active": "#409eff"}
    assert load_icon_colors(ThemeMode.LIGHT) == {"normal": "#606266", "active": "#409eff"}


def test_python_ui_files_do_not_embed_colors_or_stylesheets() -> None:
    violations: list[str] = []
    for root in (UI_ROOT / "views", UI_ROOT / "widgets"):
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            embeds_color = re.search(r"#[0-9a-fA-F]{3,8}", source) is not None
            embeds_stylesheet = '.setStyleSheet("' in source or ".setStyleSheet('" in source
            if embeds_color or embeds_stylesheet:
                violations.append(str(path.relative_to(REPOSITORY_ROOT)))

    assert violations == []
