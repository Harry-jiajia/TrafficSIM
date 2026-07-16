import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
UI_ROOT = REPOSITORY_ROOT / "ui"


def test_ui_does_not_import_backend_python_packages() -> None:
    violations: dict[str, list[str]] = {}
    for path in UI_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        modules = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        ]
        modules.extend(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        forbidden = sorted(module for module in modules if module.startswith("trafficverse"))
        if forbidden:
            violations[str(path.relative_to(REPOSITORY_ROOT))] = forbidden
    assert violations == {}
