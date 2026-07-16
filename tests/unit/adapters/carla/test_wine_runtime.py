from pathlib import Path

import pytest

from trafficverse.adapters.carla.wine_runtime import WineBridgeSettings, _wine_path


def test_wine_path_maps_absolute_posix_path_to_z_drive(tmp_path: Path) -> None:
    source = tmp_path / "runtime" / "python.exe"

    mapped = _wine_path(source)

    assert mapped.startswith("Z:\\")
    assert mapped.endswith("\\runtime\\python.exe")


def test_wine_bridge_settings_resolve_configured_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = tmp_path / "CARLA.app"
    wine = app / "Contents/SharedSupport/wine/bin/wine"
    prefix = app / "Contents/SharedSupport/prefix"
    python = tmp_path / "runtime/python.exe"
    bridge = tmp_path / "scripts/dev/wine_carla_bridge.py"
    for file_path in (wine, python, bridge):
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.touch()
    prefix.mkdir(parents=True)
    monkeypatch.setenv("TRAFFICVERSE_CARLA_APP", str(app))
    monkeypatch.setenv("TRAFFICVERSE_CARLA_WINE_PYTHON", str(python))

    settings = WineBridgeSettings.from_environment(tmp_path)

    assert settings.wine_executable == wine.resolve()
    assert settings.wine_prefix == prefix.resolve()
    assert settings.python_executable == python.resolve()
    assert settings.bridge_script == bridge.resolve()
