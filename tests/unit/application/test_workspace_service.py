from __future__ import annotations

import asyncio
from uuid import UUID

import pytest

from trafficverse.adapters.persistence import InMemoryWorkspaceRepository
from trafficverse.application.workspace_service import WorkspaceService
from trafficverse.domain.enums import ErrorCode
from trafficverse.domain.errors import TrafficVerseError
from trafficverse.domain.models import WorkspaceWrite


def test_workspace_crud_search_and_mock_overview() -> None:
    async def exercise() -> None:
        service = WorkspaceService(InMemoryWorkspaceRepository(initial=()))

        created = await service.create(
            WorkspaceWrite(name="  北京测试区  ", description="  混合交通验证  ")
        )
        other = await service.create(WorkspaceWrite(name="上海园区", description="道路压力测试"))

        assert created.name == "北京测试区"
        assert created.description == "混合交通验证"
        assert await service.list("北京") == (created,)
        assert await service.list("压力") == (other,)

        renamed = await service.update(
            created.workspace_id,
            WorkspaceWrite(name="北京核心区", description="更新后的说明"),
        )
        overview = await service.overview(created.workspace_id)

        assert renamed.name == "北京核心区"
        assert overview.workspace_id == created.workspace_id
        assert overview.simulation_count > 0
        assert overview.recent_simulations

        await service.delete(created.workspace_id)
        with pytest.raises(TrafficVerseError) as captured:
            await service.get(created.workspace_id)
        assert captured.value.code is ErrorCode.RESOURCE_NOT_FOUND

    asyncio.run(exercise())


def test_workspace_names_are_unique_and_blank_names_are_rejected() -> None:
    async def exercise() -> None:
        service = WorkspaceService(InMemoryWorkspaceRepository(initial=()))
        await service.create(WorkspaceWrite(name="测试区"))

        with pytest.raises(TrafficVerseError) as captured:
            await service.create(WorkspaceWrite(name=" 测试区 "))
        assert captured.value.code is ErrorCode.RESOURCE_CONFLICT

        with pytest.raises(ValueError):
            await service.create(WorkspaceWrite(name="   "))

    asyncio.run(exercise())


def test_missing_workspace_update_and_delete_return_not_found() -> None:
    async def exercise() -> None:
        service = WorkspaceService(InMemoryWorkspaceRepository(initial=()))
        missing_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

        with pytest.raises(TrafficVerseError) as update_error:
            await service.update(missing_id, WorkspaceWrite(name="不存在"))
        assert update_error.value.code is ErrorCode.RESOURCE_NOT_FOUND

        with pytest.raises(TrafficVerseError) as delete_error:
            await service.delete(missing_id)
        assert delete_error.value.code is ErrorCode.RESOURCE_NOT_FOUND

    asyncio.run(exercise())
