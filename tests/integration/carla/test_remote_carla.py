import os
from pathlib import Path

import pytest

from trafficverse.cli import main


@pytest.mark.integration
@pytest.mark.carla
def test_remote_town04_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    if os.getenv("TRAFFICVERSE_CARLA_INTEGRATION") != "1":
        pytest.skip("set TRAFFICVERSE_CARLA_INTEGRATION=1 on the remote Linux runtime")
    scenario = Path("configs/scenarios/core-run-town04.yaml")

    exit_code = main(
        [
            "carla",
            "smoke",
            "--scenario",
            str(scenario),
            "--vehicles",
            "10",
            "--ticks",
            "240",
            "--required-camera-frames",
            "100",
        ]
    )

    assert exit_code == 0
    assert '"ok": true' in capsys.readouterr().out
