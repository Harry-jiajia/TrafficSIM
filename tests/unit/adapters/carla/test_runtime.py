import importlib

import pytest

from trafficverse.adapters.carla.runtime import PythonCarlaRuntime


def test_missing_sdk_explains_remote_linux_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(name: str) -> object:
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", missing)

    with pytest.raises(RuntimeError, match="remote Linux x86_64 Simulation Runtime"):
        PythonCarlaRuntime().connect("carla.internal", 2000, 30.0, 0)
