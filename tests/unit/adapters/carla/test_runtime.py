import importlib

import pytest

from trafficverse.adapters.carla.runtime import PythonCarlaRuntime


def test_missing_sdk_explains_local_carla_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(name: str) -> object:
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", missing)

    with pytest.raises(RuntimeError, match="matching local 'carla' extra"):
        PythonCarlaRuntime().connect("127.0.0.1", 2000, 30.0, 0)
