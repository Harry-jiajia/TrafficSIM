"""Process-local workspace persistence for the current database-free product shell."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID, uuid4

from trafficverse.domain.enums import ErrorCode
from trafficverse.domain.errors import TrafficVerseError
from trafficverse.domain.models import (
    AgentApiRecord,
    AgentApiWrite,
    WorkspaceRecord,
    WorkspaceWrite,
)

_DEFAULT_WORKSPACES = (
    (
        UUID("10000000-0000-0000-0000-000000000001"),
        WorkspaceWrite(
            name="北京亦庄",
            description="覆盖亦庄核心路网，面向复杂十字路口与全天候自动驾驶仿真。",
        ),
    ),
    (
        UUID("10000000-0000-0000-0000-000000000002"),
        WorkspaceWrite(
            name="北京亦庄核心区",
            description="聚焦核心区高密度交通流与信号协同。",
        ),
    ),
    (
        UUID("10000000-0000-0000-0000-000000000003"),
        WorkspaceWrite(
            name="上海浦东金桥区",
            description="面向产业园区通勤与混合交通场景。",
        ),
    ),
)


class InMemoryWorkspaceRepository:
    """Workspace CRUD adapter used until PostgreSQL product persistence is wired."""

    def __init__(
        self,
        initial: Sequence[tuple[UUID, WorkspaceWrite]] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        values = _DEFAULT_WORKSPACES if initial is None else initial
        self._records = {
            workspace_id: WorkspaceRecord(
                workspace_id=workspace_id,
                name=write.name,
                description=write.description,
                created_at=now,
                updated_at=now,
            )
            for workspace_id, write in values
        }
        self._agent_apis: dict[UUID, AgentApiRecord] = {}
        self._lock = asyncio.Lock()

    async def create_workspace(self, write: WorkspaceWrite) -> WorkspaceRecord:
        async with self._lock:
            self._ensure_unique_name(write.name)
            now = datetime.now(timezone.utc)
            record = WorkspaceRecord(
                workspace_id=uuid4(),
                name=write.name,
                description=write.description,
                created_at=now,
                updated_at=now,
            )
            self._records[record.workspace_id] = record
            return record

    async def get_workspace(self, workspace_id: UUID) -> WorkspaceRecord:
        async with self._lock:
            return self._require(workspace_id)

    async def list_workspaces(self, query: str | None = None) -> tuple[WorkspaceRecord, ...]:
        async with self._lock:
            normalized = (query or "").strip().casefold()
            records = tuple(self._records.values())
            if normalized:
                records = tuple(
                    record
                    for record in records
                    if normalized in record.name.casefold()
                    or normalized in record.description.casefold()
                )
            return tuple(sorted(records, key=lambda record: (record.created_at, record.name)))

    async def update_workspace(
        self,
        workspace_id: UUID,
        write: WorkspaceWrite,
    ) -> WorkspaceRecord:
        async with self._lock:
            current = self._require(workspace_id)
            self._ensure_unique_name(write.name, excluding=workspace_id)
            updated = current.model_copy(
                update={
                    "name": write.name,
                    "description": write.description,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            self._records[workspace_id] = updated
            return updated

    async def delete_workspace(self, workspace_id: UUID) -> None:
        async with self._lock:
            self._require(workspace_id)
            del self._records[workspace_id]
            self._agent_apis = {
                agent_api_id: record
                for agent_api_id, record in self._agent_apis.items()
                if record.workspace_id != workspace_id
            }

    async def create_agent_api(
        self,
        workspace_id: UUID,
        write: AgentApiWrite,
    ) -> AgentApiRecord:
        async with self._lock:
            self._require(workspace_id)
            normalized_name = write.name.casefold()
            if any(
                record.workspace_id == workspace_id and record.name.casefold() == normalized_name
                for record in self._agent_apis.values()
            ):
                raise TrafficVerseError(
                    ErrorCode.RESOURCE_CONFLICT,
                    f"agent API name already exists in workspace: {write.name}",
                )
            now = datetime.now(timezone.utc)
            record = AgentApiRecord(
                agent_api_id=uuid4(),
                workspace_id=workspace_id,
                name=write.name,
                api_base_url=write.api_base_url,
                model_id=write.model_id,
                credential_env_var=write.credential_env_var,
                description=write.description,
                created_at=now,
                updated_at=now,
            )
            self._agent_apis[record.agent_api_id] = record
            return record

    async def list_agent_apis(self, workspace_id: UUID) -> tuple[AgentApiRecord, ...]:
        async with self._lock:
            self._require(workspace_id)
            records = (
                record
                for record in self._agent_apis.values()
                if record.workspace_id == workspace_id
            )
            return tuple(sorted(records, key=lambda record: (record.created_at, record.name)))

    async def delete_agent_api(self, workspace_id: UUID, agent_api_id: UUID) -> None:
        async with self._lock:
            self._require(workspace_id)
            record = self._agent_apis.get(agent_api_id)
            if record is None or record.workspace_id != workspace_id:
                raise TrafficVerseError(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    f"agent API does not exist: {agent_api_id}",
                )
            del self._agent_apis[agent_api_id]

    def _require(self, workspace_id: UUID) -> WorkspaceRecord:
        try:
            return self._records[workspace_id]
        except KeyError as error:
            raise TrafficVerseError(
                ErrorCode.RESOURCE_NOT_FOUND,
                f"workspace does not exist: {workspace_id}",
            ) from error

    def _ensure_unique_name(self, name: str, *, excluding: UUID | None = None) -> None:
        normalized = name.strip().casefold()
        if any(
            record.workspace_id != excluding and record.name.casefold() == normalized
            for record in self._records.values()
        ):
            raise TrafficVerseError(
                ErrorCode.RESOURCE_CONFLICT,
                f"workspace name already exists: {name}",
            )
