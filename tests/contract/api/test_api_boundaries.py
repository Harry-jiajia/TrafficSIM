import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
HANDLER_ROOTS = (
    REPOSITORY_ROOT / "src/trafficverse/api/rest",
    REPOSITORY_ROOT / "src/trafficverse/api/websocket",
)
FORBIDDEN_PREFIXES = (
    "carla",
    "sqlalchemy",
    "trafficverse.adapters.carla",
    "trafficverse.adapters.traffic",
)


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return tuple(modules)


def test_handlers_do_not_depend_on_simulator_or_database_implementations() -> None:
    violations: dict[str, list[str]] = {}
    for root in HANDLER_ROOTS:
        for path in root.rglob("*.py"):
            forbidden = sorted(
                module for module in _imports(path) if module.startswith(FORBIDDEN_PREFIXES)
            )
            if forbidden:
                violations[str(path.relative_to(REPOSITORY_ROOT))] = forbidden
    assert violations == {}
