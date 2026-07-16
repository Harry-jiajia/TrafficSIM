"""Process-local experiment state adapter for the database-free Core Run."""

from __future__ import annotations

import asyncio
from uuid import UUID

from trafficverse.domain.enums import ErrorCode, ExperimentStatus
from trafficverse.domain.errors import TrafficVerseError
from trafficverse.domain.models import DomainEvent, MetricSample


class InMemoryExperimentRepository:
    def __init__(self) -> None:
        self._statuses: dict[UUID, ExperimentStatus] = {}
        self._events: dict[UUID, list[DomainEvent]] = {}
        self._metrics: dict[UUID, list[MetricSample]] = {}
        self._lock = asyncio.Lock()

    async def create(self, experiment_id: UUID) -> None:
        async with self._lock:
            if experiment_id in self._statuses:
                raise TrafficVerseError(
                    ErrorCode.RESOURCE_CONFLICT,
                    f"experiment already exists: {experiment_id}",
                )
            self._statuses[experiment_id] = ExperimentStatus.CREATED

    async def get_status(self, experiment_id: UUID) -> ExperimentStatus:
        async with self._lock:
            try:
                return self._statuses[experiment_id]
            except KeyError as error:
                raise TrafficVerseError(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    f"experiment does not exist: {experiment_id}",
                ) from error

    async def set_status(
        self,
        experiment_id: UUID,
        status: ExperimentStatus,
        *,
        reason: str | None = None,
    ) -> None:
        del reason
        async with self._lock:
            if experiment_id not in self._statuses:
                raise TrafficVerseError(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    f"experiment does not exist: {experiment_id}",
                )
            self._statuses[experiment_id] = status

    async def append_event(self, event: DomainEvent) -> None:
        async with self._lock:
            self._events.setdefault(event.experiment_id, []).append(event)

    async def append_metric(self, metric: MetricSample) -> None:
        async with self._lock:
            self._metrics.setdefault(metric.experiment_id, []).append(metric)
