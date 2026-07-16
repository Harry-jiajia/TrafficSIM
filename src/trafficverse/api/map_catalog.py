"""Validated built-in and imported map publication service."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID, uuid4

import yaml

from trafficverse.api.models import MapImportJob, MapSummary
from trafficverse.config.loader import load_map_manifest, validate_map_manifest
from trafficverse.config.models import MapManifest
from trafficverse.domain.enums import ErrorCode
from trafficverse.domain.errors import TrafficVerseError
from trafficverse.maps.compiler import OpenDriveMapCompiler
from trafficverse.maps.errors import MapCompileError


def _validate_manifest(path: Path) -> MapManifest:
    manifest = load_map_manifest(path)
    return validate_map_manifest(
        path,
        expected_carla_version=manifest.carla_version,
        expected_network_schema_version=manifest.network_schema_version,
    )


class MapCatalog:
    def __init__(
        self,
        built_in_directories: tuple[Path, ...],
        *,
        artifact_root: Path,
        maximum_upload_bytes: int = 20 * 1024 * 1024,
    ) -> None:
        if maximum_upload_bytes <= 0:
            raise ValueError("maximum map upload size must be positive")
        self._artifact_root = artifact_root
        self._maximum_upload_bytes = maximum_upload_bytes
        self._directories: dict[str, Path] = {}
        self._jobs: dict[UUID, MapImportJob] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        for directory in built_in_directories:
            manifest = _validate_manifest(directory / "manifest.yaml")
            self._directories[manifest.map_id] = directory

    @property
    def maximum_upload_bytes(self) -> int:
        return self._maximum_upload_bytes

    def list_maps(self) -> tuple[MapSummary, ...]:
        summaries = []
        for map_id, directory in sorted(self._directories.items()):
            manifest = _validate_manifest(directory / "manifest.yaml")
            summaries.append(
                MapSummary(
                    map_id=map_id,
                    carla_map=manifest.carla_map,
                    carla_version=manifest.carla_version,
                    validated=manifest.validated,
                    network_schema_version=manifest.network_schema_version,
                )
            )
        return tuple(summaries)

    def manifest(self, map_id: str) -> MapManifest:
        directory = self._require_directory(map_id)
        return _validate_manifest(directory / "manifest.yaml")

    def directory(self, map_id: str) -> Path:
        return self._require_directory(map_id)

    def network_geojson(self, map_id: str) -> dict[str, object]:
        directory = self._require_directory(map_id)
        payload = json.loads((directory / "network.geojson").read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TrafficVerseError(ErrorCode.MAP_ASSET_INVALID, "network GeoJSON is invalid")
        return payload

    async def import_opendrive(self, payload: bytes) -> MapImportJob:
        if not payload:
            raise TrafficVerseError(ErrorCode.MAP_ASSET_INVALID, "OpenDRIVE upload is empty")
        if len(payload) > self._maximum_upload_bytes:
            raise TrafficVerseError(
                ErrorCode.MAP_ASSET_INVALID,
                "OpenDRIVE upload exceeds the configured size limit",
            )
        job_id = uuid4()
        job = MapImportJob(job_id=job_id, status="PENDING")
        self._jobs[job_id] = job
        task = asyncio.create_task(self._compile(job_id, payload))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    def import_job(self, job_id: UUID) -> MapImportJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise TrafficVerseError(
                ErrorCode.RESOURCE_NOT_FOUND,
                f"map import job does not exist: {job_id}",
            )
        return job

    async def wait_for_job(self, job_id: UUID) -> MapImportJob:
        while self.import_job(job_id).status in {"PENDING", "RUNNING"}:
            await asyncio.sleep(0)
        return self.import_job(job_id)

    async def close(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _compile(self, job_id: UUID, payload: bytes) -> None:
        self._jobs[job_id] = self._jobs[job_id].model_copy(update={"status": "RUNNING"})
        map_id = f"imported-{job_id}"
        job_root = self._artifact_root / str(job_id)
        source = job_root / "staging" / "source.xodr"
        output = job_root / "published"
        try:
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(payload)
            compiler = OpenDriveMapCompiler()
            await asyncio.to_thread(
                compiler.compile,
                source,
                output,
                map_id=map_id,
            )
            _validate_manifest(output / "manifest.yaml")
            self._directories[map_id] = output
            self._jobs[job_id] = self._jobs[job_id].model_copy(
                update={"status": "SUCCEEDED", "map_id": map_id}
            )
        except (MapCompileError, OSError, ValueError, yaml.YAMLError) as error:
            self._jobs[job_id] = self._jobs[job_id].model_copy(
                update={
                    "status": "FAILED",
                    "error_code": ErrorCode.MAP_ASSET_INVALID.value,
                    "errors": (str(error),),
                }
            )

    def _require_directory(self, map_id: str) -> Path:
        directory = self._directories.get(map_id)
        if directory is None:
            raise TrafficVerseError(
                ErrorCode.RESOURCE_NOT_FOUND,
                f"map does not exist: {map_id}",
            )
        return directory
