from __future__ import annotations

import asyncio
from pathlib import Path

from trafficverse.api.map_catalog import MapCatalog

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MAP_DIRECTORY = REPOSITORY_ROOT / "configs/maps/town04"


def test_catalog_publishes_builtin_map_and_geojson(tmp_path: Path) -> None:
    catalog = MapCatalog((MAP_DIRECTORY,), artifact_root=tmp_path)

    maps = catalog.list_maps()

    assert len(maps) == 1
    assert maps[0].validated
    assert catalog.network_geojson(maps[0].map_id)["type"] == "FeatureCollection"


def test_town04_upload_compiles_as_async_job(tmp_path: Path) -> None:
    async def exercise() -> None:
        catalog = MapCatalog((MAP_DIRECTORY,), artifact_root=tmp_path)
        job = await catalog.import_opendrive((MAP_DIRECTORY / "Town04.xodr").read_bytes())

        completed = await catalog.wait_for_job(job.job_id)

        assert completed.status == "SUCCEEDED"
        assert completed.map_id is not None
        assert catalog.manifest(completed.map_id).validated
        await catalog.close()

    asyncio.run(exercise())


def test_invalid_upload_has_structured_failed_job(tmp_path: Path) -> None:
    async def exercise() -> None:
        catalog = MapCatalog((MAP_DIRECTORY,), artifact_root=tmp_path)
        job = await catalog.import_opendrive(b"<not-opendrive />")

        completed = await catalog.wait_for_job(job.job_id)

        assert completed.status == "FAILED"
        assert completed.error_code == "MAP_ASSET_INVALID"
        assert completed.errors
        await catalog.close()

    asyncio.run(exercise())
