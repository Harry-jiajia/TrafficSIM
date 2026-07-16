"""Bounded per-experiment serial command queues."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import TypeAdapter

from trafficverse.api.dependencies import RuntimeDirectory
from trafficverse.api.models import (
    CommandOutcome,
    SetSpeedRequest,
    StopExperimentRequest,
    VehicleControlRequest,
)
from trafficverse.domain.enums import ErrorCode
from trafficverse.domain.errors import TrafficVerseError
from trafficverse.domain.models import ControlCommand

CommandType = Literal[
    "experiment.prepare",
    "experiment.start",
    "experiment.pause",
    "experiment.resume",
    "experiment.stop",
    "experiment.speed.set",
    "vehicle.control",
]
_COMMAND_TYPES: TypeAdapter[CommandType] = TypeAdapter(CommandType)


@dataclass(frozen=True, slots=True)
class _QueuedCommand:
    command_type: CommandType
    payload: object
    result: asyncio.Future[CommandOutcome]


class ExperimentCommandBus:
    def __init__(self, runtimes: RuntimeDirectory, *, queue_capacity: int = 64) -> None:
        if queue_capacity <= 0:
            raise ValueError("command queue capacity must be positive")
        self._runtimes = runtimes
        self._queue_capacity = queue_capacity
        self._queues: dict[UUID, asyncio.Queue[_QueuedCommand | None]] = {}
        self._workers: dict[UUID, asyncio.Task[None]] = {}

    async def execute(
        self,
        experiment_id: UUID,
        command_type: str,
        payload: object,
    ) -> CommandOutcome:
        parsed_type = _COMMAND_TYPES.validate_python(command_type)
        queue = self._queues.get(experiment_id)
        if queue is None:
            queue = asyncio.Queue(maxsize=self._queue_capacity)
            self._queues[experiment_id] = queue
            self._workers[experiment_id] = asyncio.create_task(self._worker(experiment_id, queue))
        if queue.full():
            manager = await self._runtimes.get(experiment_id)
            return CommandOutcome(
                accepted=False,
                status=await manager.get_status(),
                error_code=ErrorCode.RESOURCE_CONFLICT.value,
                message="experiment command queue is full",
            )
        loop = asyncio.get_running_loop()
        result: asyncio.Future[CommandOutcome] = loop.create_future()
        await queue.put(_QueuedCommand(parsed_type, payload, result))
        return await result

    async def close(self) -> None:
        for queue in self._queues.values():
            await queue.put(None)
        if self._workers:
            await asyncio.gather(*self._workers.values(), return_exceptions=True)
        self._queues.clear()
        self._workers.clear()

    async def _worker(
        self,
        experiment_id: UUID,
        queue: asyncio.Queue[_QueuedCommand | None],
    ) -> None:
        while True:
            queued = await queue.get()
            if queued is None:
                return
            try:
                outcome = await self._apply(experiment_id, queued.command_type, queued.payload)
            except TrafficVerseError as error:
                manager = await self._runtimes.get(experiment_id)
                outcome = CommandOutcome(
                    accepted=False,
                    status=await manager.get_status(),
                    error_code=error.code.value,
                    message=error.message,
                )
            except Exception as error:
                manager = await self._runtimes.get(experiment_id)
                outcome = CommandOutcome(
                    accepted=False,
                    status=await manager.get_status(),
                    error_code=ErrorCode.COMPONENT_UNAVAILABLE.value,
                    message=str(error),
                )
            if not queued.result.done():
                queued.result.set_result(outcome)

    async def _apply(
        self,
        experiment_id: UUID,
        command_type: CommandType,
        payload: object,
    ) -> CommandOutcome:
        manager = await self._runtimes.get(experiment_id)
        if command_type == "experiment.prepare":
            await manager.prepare(experiment_id)
        elif command_type == "experiment.start":
            await manager.start()
        elif command_type == "experiment.pause":
            await manager.pause()
        elif command_type == "experiment.resume":
            await manager.resume()
        elif command_type == "experiment.stop":
            stop_request = StopExperimentRequest.model_validate(payload)
            await manager.stop(stop_request.reason)
        elif command_type == "experiment.speed.set":
            speed_request = SetSpeedRequest.model_validate(payload)
            await manager.set_speed(speed_request.multiplier)
        else:
            control_request = VehicleControlRequest.model_validate(payload)
            await manager.control_vehicle(
                control_request.vehicle_id,
                ControlCommand(
                    desired_acceleration_mps2=control_request.desired_acceleration_mps2,
                    desired_speed_mps=control_request.desired_speed_mps,
                    lane_change=control_request.lane_change,
                    takeover_requested=control_request.takeover_requested,
                    stop_requested=control_request.stop_requested,
                ),
            )
        return CommandOutcome(accepted=True, status=await manager.get_status())
