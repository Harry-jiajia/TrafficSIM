from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_editable_console_environment_can_import_ui(tmp_path: Path) -> None:
    probe = tmp_path / "import_ui.py"
    probe.write_text("import ui\n", encoding="utf-8")
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [sys.executable, str(probe)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
