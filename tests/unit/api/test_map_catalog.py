from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import pytest

from trafficverse.api.map_catalog import MapCatalog
from trafficverse.domain.enums import ErrorCode
from trafficverse.domain.errors import TrafficVerseError

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


def _sumo_package(directory: Path, *, missing_network: bool = False) -> None:
    directory.mkdir()
    if not missing_network:
        (directory / "scene.net.xml").write_text(
            """<net>
  <edge id="a"><lane id="a_0" speed="10" shape="0,0 10,0"/></edge>
  <edge id="b"><lane id="b_0" speed="10" shape="11,1 20,1"/></edge>
  <connection from="a" to="b" fromLane="0" toLane="0" tl="j" linkIndex="0"/>
</net>\n""",
            encoding="utf-8",
        )
    (directory / "scene.rou.xml").write_text("<routes/>\n", encoding="utf-8")
    (directory / "scene.sumocfg").write_text(
        """<configuration><input>
  <net-file value="scene.net.xml"/><route-files value="scene.rou.xml"/>
</input><time><step-length value="0.5"/><end value="10"/></time></configuration>\n""",
        encoding="utf-8",
    )


def test_catalog_discovers_native_sumo_package_and_generates_geojson(tmp_path: Path) -> None:
    directory = tmp_path / "direct-sumo"
    _sumo_package(directory)
    catalog = MapCatalog((directory,), artifact_root=tmp_path / "artifacts", package_root=tmp_path)

    summary = catalog.list_maps()[0]
    package = catalog.sumo_package(summary.map_id)
    network = catalog.network_geojson(summary.map_id)

    assert summary.kind == "sumo"
    assert summary.map_id == "direct-sumo"
    assert summary.sumo_step_ms == 500
    assert not summary.manifest_available
    assert package is not None and package.config_path.name == "scene.sumocfg"
    assert network["type"] == "FeatureCollection"
    features = cast("list[dict[str, object]]", network["features"])
    assert any(
        cast("dict[str, object]", feature.get("properties", {})).get("signal_id") == "sumo-tls:j:0"
        for feature in features
    )


def test_invalid_sumo_package_does_not_block_other_catalog_entries(tmp_path: Path) -> None:
    valid = tmp_path / "valid"
    invalid = tmp_path / "invalid"
    _sumo_package(valid)
    _sumo_package(invalid, missing_network=True)
    catalog = MapCatalog(
        (invalid, valid),
        artifact_root=tmp_path / "artifacts",
        package_root=tmp_path,
    )

    summaries = {item.map_id: item for item in catalog.list_maps()}

    assert summaries["valid"].validated
    assert not summaries["invalid"].validated
    assert summaries["invalid"].validation_errors
    with pytest.raises(TrafficVerseError) as captured:
        catalog.sumo_package("invalid")
    assert captured.value.code is ErrorCode.MAP_ASSET_INVALID
