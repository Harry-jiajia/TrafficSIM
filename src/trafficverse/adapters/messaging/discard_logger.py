"""Explicit no-persistence data sink for the database-free Core Run."""

from trafficverse.domain.models import DomainEvent, SimulationFrame


class DiscardDataLogger:
    async def record_frame(self, frame: SimulationFrame) -> None:
        del frame

    async def record_event(self, event: DomainEvent) -> None:
        del event

    async def flush(self) -> None:
        return
