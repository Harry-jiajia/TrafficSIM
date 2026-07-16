"""Versioned WebSocket command and live-state gateway."""

from __future__ import annotations

import asyncio
import time
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from trafficverse.adapters.messaging import Subscription, make_envelope
from trafficverse.api.dependencies import ApiDependencies
from trafficverse.api.models import ClientCommand, SubscribeRequest
from trafficverse.domain.errors import TrafficVerseError


def _sequence(dependencies: ApiDependencies, experiment_id: UUID) -> int:
    snapshot = dependencies.broker.world_snapshot(experiment_id)
    return 0 if snapshot is None else snapshot.sequence


async def _offer_command_result(
    dependencies: ApiDependencies,
    subscription: Subscription,
    command: ClientCommand,
) -> None:
    try:
        outcome = await dependencies.commands.execute(
            command.experiment_id,
            command.type,
            command.payload,
        )
        manager = await dependencies.runtimes.get(command.experiment_id)
        message_type = "command.accepted" if outcome.accepted else "command.rejected"
        subscription.offer(
            make_envelope(
                message_type,
                command.experiment_id,
                simulation_time_ms=manager.simulation_time_ms,
                sequence=_sequence(dependencies, command.experiment_id),
                correlation_id=command.message_id,
                payload=outcome.model_dump(mode="json"),
            )
        )
        if outcome.accepted and command.type.startswith("experiment."):
            subscription.offer(
                make_envelope(
                    "experiment.state.changed",
                    command.experiment_id,
                    simulation_time_ms=manager.simulation_time_ms,
                    sequence=_sequence(dependencies, command.experiment_id),
                    payload={"status": outcome.status.value},
                )
            )
    except (TrafficVerseError, ValidationError, ValueError) as error:
        manager = await dependencies.runtimes.get(command.experiment_id)
        code = getattr(getattr(error, "code", None), "value", "COMMAND_INVALID")
        subscription.offer(
            make_envelope(
                "command.rejected",
                command.experiment_id,
                simulation_time_ms=manager.simulation_time_ms,
                sequence=_sequence(dependencies, command.experiment_id),
                correlation_id=command.message_id,
                payload={"accepted": False, "error_code": code, "message": str(error)},
            )
        )


async def _send_loop(
    websocket: WebSocket,
    subscription: Subscription,
    last_received: list[float],
) -> None:
    while True:
        if subscription.buffer.overflowed:
            await websocket.close(code=4408, reason="critical message queue overflow")
            return
        try:
            message = await asyncio.wait_for(subscription.buffer.next(), timeout=15.0)
        except asyncio.TimeoutError:
            if time.monotonic() - last_received[0] > 45.0:
                await websocket.close(code=4408, reason="heartbeat timeout")
                return
            message = make_envelope(
                "heartbeat.ping",
                subscription.experiment_id,
                simulation_time_ms=0,
                sequence=0,
                payload={},
            )
        await websocket.send_json(message.model_dump(mode="json"))


async def _offer_health(
    dependencies: ApiDependencies,
    subscription: Subscription,
    experiment_id: UUID,
    *,
    simulation_time_ms: int,
) -> None:
    components = await dependencies.readiness()
    subscription.offer(
        make_envelope(
            "component.health",
            experiment_id,
            simulation_time_ms=simulation_time_ms,
            sequence=_sequence(dependencies, experiment_id),
            payload={"components": [component.model_dump(mode="json") for component in components]},
        )
    )


def build_router(dependencies: ApiDependencies) -> APIRouter:
    router = APIRouter()

    @router.websocket("/api/v1/ws")
    async def websocket_endpoint(websocket: WebSocket, experiment_id: UUID) -> None:
        try:
            manager = await dependencies.runtimes.get(experiment_id)
        except TrafficVerseError:
            await websocket.close(code=4404, reason="experiment runtime not found")
            return
        await websocket.accept()
        subscription = dependencies.broker.subscribe(experiment_id)
        last_received = [time.monotonic()]
        subscription.offer(
            make_envelope(
                "session.ready",
                experiment_id,
                simulation_time_ms=manager.simulation_time_ms,
                sequence=_sequence(dependencies, experiment_id),
                payload={"status": (await manager.get_status()).value},
            )
        )
        sender = asyncio.create_task(_send_loop(websocket, subscription, last_received))
        try:
            while True:
                payload = await websocket.receive_json()
                last_received[0] = time.monotonic()
                try:
                    command = ClientCommand.model_validate(payload)
                    if command.experiment_id != experiment_id:
                        raise ValueError("command experiment_id does not match the session")
                except (ValidationError, ValueError) as error:
                    subscription.offer(
                        make_envelope(
                            "error",
                            experiment_id,
                            simulation_time_ms=manager.simulation_time_ms,
                            sequence=_sequence(dependencies, experiment_id),
                            payload={"code": "MESSAGE_INVALID", "message": str(error)},
                        )
                    )
                    continue
                if command.type == "heartbeat.pong":
                    continue
                if command.type == "subscribe":
                    try:
                        request = SubscribeRequest.model_validate(command.payload)
                        subscription.set_topics(frozenset(request.topics), max_hz=request.max_hz)
                    except (ValidationError, ValueError) as error:
                        subscription.offer(
                            make_envelope(
                                "command.rejected",
                                experiment_id,
                                simulation_time_ms=manager.simulation_time_ms,
                                sequence=_sequence(dependencies, experiment_id),
                                correlation_id=command.message_id,
                                payload={
                                    "accepted": False,
                                    "error_code": "SUBSCRIPTION_INVALID",
                                    "message": str(error),
                                },
                            )
                        )
                        continue
                    snapshot = dependencies.broker.world_snapshot(experiment_id)
                    if snapshot is not None:
                        subscription.offer(snapshot)
                    await _offer_health(
                        dependencies,
                        subscription,
                        experiment_id,
                        simulation_time_ms=manager.simulation_time_ms,
                    )
                    subscription.offer(
                        make_envelope(
                            "command.accepted",
                            experiment_id,
                            simulation_time_ms=manager.simulation_time_ms,
                            sequence=_sequence(dependencies, experiment_id),
                            correlation_id=command.message_id,
                            payload={"accepted": True},
                        )
                    )
                    continue
                if command.type == "world.snapshot.request":
                    snapshot = dependencies.broker.world_snapshot(experiment_id)
                    if snapshot is None:
                        subscription.offer(
                            make_envelope(
                                "command.rejected",
                                experiment_id,
                                simulation_time_ms=manager.simulation_time_ms,
                                sequence=0,
                                correlation_id=command.message_id,
                                payload={
                                    "accepted": False,
                                    "error_code": "SNAPSHOT_UNAVAILABLE",
                                    "message": "world snapshot is not available yet",
                                },
                            )
                        )
                    else:
                        subscription.offer(snapshot)
                    continue
                await _offer_command_result(dependencies, subscription, command)
        except (WebSocketDisconnect, EOFError):
            pass
        finally:
            subscription.close()
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)

    return router
