"""Core Run REST resources."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Query, Response, UploadFile, status
from fastapi.responses import JSONResponse

from trafficverse.api.command_bus import ExperimentCommandBus
from trafficverse.api.dependencies import ApiDependencies
from trafficverse.api.models import (
    CommandOutcome,
    ExperimentCreateRequest,
    ExperimentView,
    HealthResponse,
    MapImportJob,
    MapSummary,
    ReadinessResponse,
    SetSpeedRequest,
    StopExperimentRequest,
    WorkspaceCreateRequest,
    WorkspaceUpdateRequest,
    WorkspaceView,
)
from trafficverse.domain.enums import ErrorCode
from trafficverse.domain.errors import TrafficVerseError
from trafficverse.domain.models import WorkspaceOverview, WorkspaceRecord, WorkspaceWrite


def _require_accepted(outcome: CommandOutcome) -> None:
    if not outcome.accepted:
        code = ErrorCode(outcome.error_code or ErrorCode.RESOURCE_CONFLICT.value)
        raise TrafficVerseError(code, outcome.message or "command was rejected")


def _workspace_view(record: WorkspaceRecord) -> WorkspaceView:
    return WorkspaceView.model_validate(record.model_dump())


async def _execute(
    commands: ExperimentCommandBus,
    experiment_id: UUID,
    command_type: str,
    payload: object,
) -> CommandOutcome:
    outcome = await commands.execute(experiment_id, command_type, payload)
    _require_accepted(outcome)
    return outcome


def build_router(dependencies: ApiDependencies) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @router.get("/ready", response_model=ReadinessResponse)
    async def ready(response: Response) -> ReadinessResponse:
        components = await dependencies.readiness()
        is_ready = all(
            not component.required or component.status.value in {"HEALTHY", "DISABLED"}
            for component in components
        )
        if not is_ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(ready=is_ready, components=components)

    @router.get("/maps", response_model=tuple[MapSummary, ...])
    async def maps() -> tuple[MapSummary, ...]:
        return dependencies.maps.list_maps()

    @router.get("/workspaces", response_model=tuple[WorkspaceView, ...])
    async def list_workspaces(
        query: Annotated[str | None, Query(max_length=200)] = None,
    ) -> tuple[WorkspaceView, ...]:
        records = await dependencies.workspaces.list(query)
        return tuple(_workspace_view(record) for record in records)

    @router.post(
        "/workspaces",
        response_model=WorkspaceView,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_workspace(request: WorkspaceCreateRequest) -> WorkspaceView:
        record = await dependencies.workspaces.create(
            WorkspaceWrite(name=request.name, description=request.description)
        )
        return _workspace_view(record)

    @router.patch("/workspaces/{workspace_id}", response_model=WorkspaceView)
    async def update_workspace(
        workspace_id: UUID,
        request: WorkspaceUpdateRequest,
    ) -> WorkspaceView:
        record = await dependencies.workspaces.update(
            workspace_id,
            WorkspaceWrite(name=request.name, description=request.description),
        )
        return _workspace_view(record)

    @router.delete(
        "/workspaces/{workspace_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    async def delete_workspace(workspace_id: UUID) -> Response:
        await dependencies.workspaces.delete(workspace_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get(
        "/workspaces/{workspace_id}/overview",
        response_model=WorkspaceOverview,
    )
    async def workspace_overview(workspace_id: UUID) -> WorkspaceOverview:
        return await dependencies.workspaces.overview(workspace_id)

    @router.get("/maps/{map_id}/manifest")
    async def map_manifest(map_id: str) -> object:
        return dependencies.maps.manifest(map_id).model_dump(mode="json")

    @router.get("/maps/{map_id}/network")
    async def map_network(map_id: str) -> JSONResponse:
        return JSONResponse(
            dependencies.maps.network_geojson(map_id),
            media_type="application/geo+json",
        )

    @router.post(
        "/maps/import",
        response_model=MapImportJob,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def import_map(file: Annotated[UploadFile, File()]) -> MapImportJob:
        if not file.filename or not file.filename.lower().endswith(".xodr"):
            raise TrafficVerseError(
                ErrorCode.MAP_ASSET_INVALID,
                "map import requires an .xodr file",
            )
        payload = await file.read(dependencies.maps.maximum_upload_bytes + 1)
        return await dependencies.maps.import_opendrive(payload)

    @router.get("/maps/import/{job_id}", response_model=MapImportJob)
    async def import_status(job_id: UUID) -> MapImportJob:
        return dependencies.maps.import_job(job_id)

    @router.post(
        "/experiments",
        response_model=ExperimentView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_experiment(request: ExperimentCreateRequest) -> ExperimentView:
        await dependencies.workspaces.get(request.workspace_id)
        return await dependencies.runtimes.create(
            uuid4(),
            request.workspace_id,
            request.scenario_id,
            request.map_id,
        )

    @router.get("/experiments/{experiment_id}", response_model=ExperimentView)
    async def get_experiment(experiment_id: UUID) -> ExperimentView:
        return await dependencies.runtimes.view(experiment_id)

    @router.post("/experiments/{experiment_id}/prepare", response_model=ExperimentView)
    async def prepare_experiment(experiment_id: UUID) -> ExperimentView:
        await _execute(dependencies.commands, experiment_id, "experiment.prepare", {})
        return await dependencies.runtimes.view(experiment_id)

    @router.post("/experiments/{experiment_id}/start", response_model=ExperimentView)
    async def start_experiment(experiment_id: UUID) -> ExperimentView:
        await _execute(dependencies.commands, experiment_id, "experiment.start", {})
        return await dependencies.runtimes.view(experiment_id)

    @router.post("/experiments/{experiment_id}/pause", response_model=ExperimentView)
    async def pause_experiment(experiment_id: UUID) -> ExperimentView:
        await _execute(dependencies.commands, experiment_id, "experiment.pause", {})
        return await dependencies.runtimes.view(experiment_id)

    @router.post("/experiments/{experiment_id}/resume", response_model=ExperimentView)
    async def resume_experiment(experiment_id: UUID) -> ExperimentView:
        await _execute(dependencies.commands, experiment_id, "experiment.resume", {})
        return await dependencies.runtimes.view(experiment_id)

    @router.post("/experiments/{experiment_id}/stop", response_model=ExperimentView)
    async def stop_experiment(
        experiment_id: UUID, request: StopExperimentRequest
    ) -> ExperimentView:
        await _execute(dependencies.commands, experiment_id, "experiment.stop", request)
        return await dependencies.runtimes.view(experiment_id)

    @router.post("/experiments/{experiment_id}/speed", response_model=ExperimentView)
    async def set_speed(experiment_id: UUID, request: SetSpeedRequest) -> ExperimentView:
        await _execute(dependencies.commands, experiment_id, "experiment.speed.set", request)
        return await dependencies.runtimes.view(experiment_id)

    return router
