import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from trafficverse.application.scenario_service import ScenarioDraft, ScenarioService
from trafficverse.config.loader import configuration_hash, load_scenario
from trafficverse.domain.enums import ErrorCode
from trafficverse.domain.errors import TrafficVerseError
from trafficverse.domain.models import (
    MapAssetRegistration,
    ScenarioListQuery,
    ScenarioPage,
    ScenarioRecord,
    ScenarioVersionRecord,
    ScenarioWrite,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_PATH = REPOSITORY_ROOT / "configs/scenarios/core-run-town04.yaml"


class InMemoryScenarioRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, ScenarioRecord] = {}

    async def register_map_asset(self, asset: MapAssetRegistration) -> None:
        del asset

    async def create_scenario(self, write: ScenarioWrite) -> ScenarioRecord:
        now = datetime.now(timezone.utc)
        scenario_id = uuid4()
        version = ScenarioVersionRecord(
            scenario_version_id=uuid4(),
            scenario_id=scenario_id,
            map_asset_id=write.map_asset_id,
            version=1,
            config=write.config,
            config_hash=write.config_hash,
            created_at=now,
        )
        record = ScenarioRecord(
            scenario_id=scenario_id,
            name=write.name,
            description=write.description,
            current_version=version,
            created_at=now,
            updated_at=now,
        )
        self.records[scenario_id] = record
        return record

    async def get_scenario(
        self, scenario_id: UUID, *, include_deleted: bool = False
    ) -> ScenarioRecord:
        record = self.records.get(scenario_id)
        if record is None or (record.deleted_at is not None and not include_deleted):
            raise TrafficVerseError(ErrorCode.RESOURCE_NOT_FOUND, "scenario not found")
        return record

    async def list_scenarios(self, query: ScenarioListQuery) -> ScenarioPage:
        records = sorted(self.records.values(), key=lambda record: str(record.scenario_id))
        if not query.include_deleted:
            records = [record for record in records if record.deleted_at is None]
        return ScenarioPage(
            items=tuple(records[query.offset : query.offset + query.limit]),
            total=len(records),
            offset=query.offset,
            limit=query.limit,
        )

    async def update_scenario(
        self,
        scenario_id: UUID,
        write: ScenarioWrite,
        *,
        expected_version: int,
    ) -> ScenarioRecord:
        current = await self.get_scenario(scenario_id)
        if current.current_version.version != expected_version:
            raise TrafficVerseError(ErrorCode.CONCURRENT_MODIFICATION, "scenario version conflict")
        now = datetime.now(timezone.utc)
        version = ScenarioVersionRecord(
            scenario_version_id=uuid4(),
            scenario_id=scenario_id,
            map_asset_id=write.map_asset_id,
            version=expected_version + 1,
            config=write.config,
            config_hash=write.config_hash,
            created_at=now,
        )
        updated = current.model_copy(
            update={
                "name": write.name,
                "description": write.description,
                "current_version": version,
                "updated_at": now,
            }
        )
        self.records[scenario_id] = updated
        return updated

    async def soft_delete_scenario(self, scenario_id: UUID) -> None:
        current = await self.get_scenario(scenario_id, include_deleted=True)
        if current.deleted_at is None:
            now = datetime.now(timezone.utc)
            self.records[scenario_id] = current.model_copy(
                update={"deleted_at": now, "updated_at": now}
            )


def test_scenario_service_crud_clone_resolve_and_soft_delete() -> None:
    async def exercise() -> None:
        config = load_scenario(SCENARIO_PATH, apply_environment=False)
        map_asset_id = uuid4()
        repository = InMemoryScenarioRepository()
        service = ScenarioService(repository)
        draft = ScenarioDraft(
            name="Town04 baseline",
            description="first version",
            map_asset_id=map_asset_id,
            config=config,
        )

        created = await service.create(draft)
        assert created.current_version.version == 1
        assert created.current_version.config_hash == configuration_hash(config)
        assert await service.resolve(created.scenario_id) == config

        updated = await service.update(
            created.scenario_id,
            draft.model_copy(update={"description": "second version"}),
            expected_version=1,
        )
        assert updated.current_version.version == 2
        assert updated.description == "second version"

        cloned = await service.clone(created.scenario_id, name="Town04 clone")
        assert cloned.scenario_id != created.scenario_id
        assert cloned.current_version.version == 1
        assert cloned.current_version.config_hash == updated.current_version.config_hash

        first_page = await service.list(ScenarioListQuery(offset=0, limit=1))
        second_page = await service.list(ScenarioListQuery(offset=1, limit=1))
        assert first_page.total == 2
        assert len(first_page.items) == len(second_page.items) == 1

        await service.delete(created.scenario_id)
        visible = await service.list(ScenarioListQuery())
        historical = await service.get(created.scenario_id, include_deleted=True)
        assert visible.total == 1
        assert historical.deleted_at is not None

    asyncio.run(exercise())
