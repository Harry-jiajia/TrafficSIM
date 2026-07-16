"""Asynchronous event and data-sink ports."""

from typing import Protocol

from trafficverse.domain.models import DomainEvent, SimulationFrame, WebSocketEnvelope


class EventPublisherPort(Protocol):
    async def publish(self, message: WebSocketEnvelope) -> None: ...


class DataLoggerPort(Protocol):
    async def record_frame(self, frame: SimulationFrame) -> None: ...

    async def record_event(self, event: DomainEvent) -> None: ...

    async def flush(self) -> None: ...
