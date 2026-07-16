"""Install the local Windows Python client used by the macOS CARLA Wine bridge."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PYTHON_VERSION = "3.12.10"
PYTHON_ARCHIVE_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
)
PYTHON_ARCHIVE_SHA256 = "156c7eea90d58cd7e91a23f28a0056616b13e9f4cf4901b7b99b837b7848c6da"
CARLA_WHEEL_NAME = "carla-0.9.16-cp312-cp312-win_amd64.whl"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare an isolated Windows CARLA 0.9.16 client for Wine on macOS."
    )
    parser.add_argument(
        "--carla-app",
        type=Path,
        default=Path.home() / "Applications" / "CARLA.app",
        help="Path to the local CARLA.app bundle.",
    )
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=Path("artifacts/runtime/wine-python312"),
        help="Ignored directory in which to install the Windows client runtime.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing runtime directory.",
    )
    return parser.parse_args()


def _wheel_path(carla_app: Path) -> Path:
    dist = (
        carla_app
        / "Contents/SharedSupport/prefix/drive_c/Program Files/CARLA_0.9.16"
        / "PythonAPI/carla/dist"
    )
    wheel = dist / CARLA_WHEEL_NAME
    if not wheel.is_file():
        raise SystemExit(f"CARLA 0.9.16 CPython 3.12 Windows wheel was not found at {wheel}")
    return wheel


def _download_python(destination: Path) -> None:
    digest = hashlib.sha256()
    with (
        urllib.request.urlopen(PYTHON_ARCHIVE_URL, timeout=60) as response,
        destination.open("wb") as output,
    ):
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            output.write(chunk)
    actual = digest.hexdigest()
    if actual != PYTHON_ARCHIVE_SHA256:
        destination.unlink(missing_ok=True)
        raise SystemExit(
            f"Windows Python archive checksum mismatch: expected "
            f"{PYTHON_ARCHIVE_SHA256}, received {actual}"
        )


def _enable_site_packages(runtime_dir: Path) -> None:
    pth = runtime_dir / "python312._pth"
    lines = pth.read_text(encoding="utf-8").splitlines()
    if r"Lib\site-packages" not in lines:
        lines.insert(-1, r"Lib\site-packages")
    pth.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    arguments = _arguments()
    carla_app = arguments.carla_app.expanduser().resolve()
    runtime_dir = arguments.runtime_dir.expanduser().resolve()
    wheel = _wheel_path(carla_app)

    if runtime_dir.exists():
        if not arguments.force:
            raise SystemExit(f"{runtime_dir} already exists; use --force to replace it")
        shutil.rmtree(runtime_dir)

    runtime_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="trafficverse-wine-python-") as temporary:
        archive = Path(temporary) / "python-embed.zip"
        _download_python(archive)
        with zipfile.ZipFile(archive) as python_zip:
            python_zip.extractall(runtime_dir)

    site_packages = runtime_dir / "Lib/site-packages"
    site_packages.mkdir(parents=True)
    with zipfile.ZipFile(wheel) as carla_wheel:
        carla_wheel.extractall(site_packages)
    _enable_site_packages(runtime_dir)

    print(f"Prepared Wine CARLA client at {runtime_dir}")


if __name__ == "__main__":
    main()
