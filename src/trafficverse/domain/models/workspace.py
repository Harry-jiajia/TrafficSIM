"""Workspace records and the temporary overview contract."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, Field, StringConstraints

from trafficverse.domain.models.common import StrictModel

WorkspaceName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


class WorkspaceWrite(StrictModel):
    name: WorkspaceName
    description: str = Field(default="", max_length=1000)


class WorkspaceRecord(StrictModel):
    workspace_id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    created_at: datetime
    updated_at: datetime


class AgentApiWrite(StrictModel):
    name: WorkspaceName
    api_base_url: AnyHttpUrl
    model_id: str = Field(min_length=1, max_length=200)
    credential_env_var: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_]*$",
    )
    description: str = Field(default="", max_length=1000)


class AgentApiRecord(StrictModel):
    agent_api_id: UUID
    workspace_id: UUID
    name: str = Field(min_length=1, max_length=200)
    api_base_url: AnyHttpUrl
    model_id: str = Field(min_length=1, max_length=200)
    credential_env_var: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=1000)
    created_at: datetime
    updated_at: datetime


class WorkspaceAutomationCount(StrictModel):
    level: str = Field(min_length=1, max_length=40)
    count: int = Field(ge=0)


class WorkspaceActivitySample(StrictModel):
    day: date
    simulations: int = Field(ge=0)


class WorkspaceRecentSimulation(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    status: Literal["SUCCEEDED", "WARNING", "FAILED"]
    occurred_at: datetime
    duration_ms: int = Field(ge=0)
    automation_summary: str = Field(min_length=1, max_length=100)


class WorkspaceOverview(StrictModel):
    """Mock-backed workspace overview kept stable for a future real data source."""

    workspace_id: UUID
    map_count: int = Field(ge=0)
    agent_count: int = Field(ge=0)
    scenario_count: int = Field(ge=0)
    simulation_count: int = Field(ge=0)
    automation_counts: tuple[WorkspaceAutomationCount, ...]
    succeeded_simulations: int = Field(ge=0)
    failed_simulations: int = Field(ge=0)
    runtime_hours: float = Field(ge=0.0)
    activity: tuple[WorkspaceActivitySample, ...]
    recent_simulations: tuple[WorkspaceRecentSimulation, ...]
    preview_region: str = Field(min_length=1, max_length=200)
