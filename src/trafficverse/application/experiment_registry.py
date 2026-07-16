"""In-process experiment isolation and explicit running-capacity control."""

import asyncio
from typing import Protocol
from uuid import UUID

from trafficverse.domain.enums import ErrorCode
from trafficverse.domain.errors import TrafficVerseError


class RegisteredExperiment(Protocol):
    @property
    def experiment_id(self) -> UUID | None: ...


class ExperimentRegistry:
    def __init__(self, *, maximum_running: int) -> None:
        if maximum_running < 1:
            raise ValueError("maximum_running must be at least one")
        self._maximum_running = maximum_running
        self._experiments: dict[UUID, RegisteredExperiment] = {}
        self._running: set[UUID] = set()
        self._lock = asyncio.Lock()

    @property
    def maximum_running(self) -> int:
        return self._maximum_running

    async def register(self, experiment_id: UUID, manager: RegisteredExperiment) -> None:
        async with self._lock:
            existing = self._experiments.get(experiment_id)
            if existing is not None and existing is not manager:
                raise TrafficVerseError(
                    ErrorCode.RESOURCE_CONFLICT,
                    f"experiment is already registered: {experiment_id}",
                )
            self._experiments[experiment_id] = manager

    async def get(self, experiment_id: UUID) -> RegisteredExperiment:
        async with self._lock:
            manager = self._experiments.get(experiment_id)
            if manager is None:
                raise TrafficVerseError(
                    ErrorCode.RESOURCE_NOT_FOUND,
                    f"experiment is not registered: {experiment_id}",
                )
            return manager

    async def acquire_running(self, experiment_id: UUID) -> None:
        async with self._lock:
            if experiment_id in self._running:
                return
            if len(self._running) >= self._maximum_running:
                raise TrafficVerseError(
                    ErrorCode.RESOURCE_CONFLICT,
                    "maximum concurrently running experiments reached",
                    details={"maximum_running": str(self._maximum_running)},
                )
            self._running.add(experiment_id)

    async def release_running(self, experiment_id: UUID) -> None:
        async with self._lock:
            self._running.discard(experiment_id)

    async def unregister(self, experiment_id: UUID) -> None:
        async with self._lock:
            self._running.discard(experiment_id)
            self._experiments.pop(experiment_id, None)
