"""Deterministic API contract generation without external runtimes."""

from pathlib import Path

from trafficverse.adapters.messaging import FrameBroker
from trafficverse.api.app import create_app
from trafficverse.api.command_bus import ExperimentCommandBus
from trafficverse.api.dependencies import ApiDependencies, RuntimeDirectory
from trafficverse.api.map_catalog import MapCatalog
from trafficverse.api.models import ReadinessComponent


def build_openapi_contract() -> dict[str, object]:
    runtimes = RuntimeDirectory()
    dependencies = ApiDependencies(
        runtimes=runtimes,
        maps=MapCatalog((), artifact_root=Path("artifacts/maps")),
        commands=ExperimentCommandBus(runtimes),
        broker=FrameBroker(),
        readiness=_empty_readiness,
    )
    return create_app(dependencies).openapi()


async def _empty_readiness() -> tuple[ReadinessComponent, ...]:
    return ()
