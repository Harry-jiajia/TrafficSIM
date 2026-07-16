"""Scenario CRUD and immutable-version use cases."""

from uuid import UUID

from pydantic import Field, JsonValue, TypeAdapter

from trafficverse.config.loader import configuration_hash
from trafficverse.config.models import ScenarioConfig
from trafficverse.domain.models import (
    ScenarioListQuery,
    ScenarioPage,
    ScenarioRecord,
    ScenarioWrite,
    StrictModel,
)
from trafficverse.ports.persistence import ScenarioRepositoryPort

_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])


class ScenarioDraft(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    map_asset_id: UUID
    config: ScenarioConfig


class ScenarioService:
    def __init__(self, repository: ScenarioRepositoryPort) -> None:
        self._repository = repository

    async def create(self, draft: ScenarioDraft) -> ScenarioRecord:
        return await self._repository.create_scenario(self._write(draft))

    async def get(self, scenario_id: UUID, *, include_deleted: bool = False) -> ScenarioRecord:
        return await self._repository.get_scenario(scenario_id, include_deleted=include_deleted)

    async def list(self, query: ScenarioListQuery) -> ScenarioPage:
        return await self._repository.list_scenarios(query)

    async def update(
        self,
        scenario_id: UUID,
        draft: ScenarioDraft,
        *,
        expected_version: int,
    ) -> ScenarioRecord:
        return await self._repository.update_scenario(
            scenario_id,
            self._write(draft),
            expected_version=expected_version,
        )

    async def clone(self, scenario_id: UUID, *, name: str) -> ScenarioRecord:
        source = await self._repository.get_scenario(scenario_id)
        write = ScenarioWrite(
            name=name,
            description=source.description,
            map_asset_id=source.current_version.map_asset_id,
            config=source.current_version.config,
            config_hash=source.current_version.config_hash,
        )
        return await self._repository.create_scenario(write)

    async def delete(self, scenario_id: UUID) -> None:
        await self._repository.soft_delete_scenario(scenario_id)

    async def resolve(self, scenario_id: UUID) -> ScenarioConfig:
        scenario = await self._repository.get_scenario(scenario_id)
        return ScenarioConfig.model_validate(scenario.current_version.config)

    @staticmethod
    def _write(draft: ScenarioDraft) -> ScenarioWrite:
        config = _JSON_OBJECT.validate_python(draft.config.model_dump(mode="json"))
        return ScenarioWrite(
            name=draft.name,
            description=draft.description,
            map_asset_id=draft.map_asset_id,
            config=config,
            config_hash=configuration_hash(draft.config),
        )
