from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from trafficverse.domain.enums import AutomationLevel, VehicleAction
from trafficverse.domain.models import Vector3, VehicleState, WebSocketEnvelope


def _vehicle() -> VehicleState:
    return VehicleState(
        experiment_id=uuid4(),
        vehicle_id="veh-1",
        simulation_time_ms=50,
        sequence=1,
        automation_level=AutomationLevel.HUMAN,
        position=Vector3(x=1.0, y=2.0),
        speed_mps=10.0,
        acceleration_mps2=0.0,
        heading_rad=0.5,
        lane_id="edge-1_0",
        controller_id="native-traffic-engine",
        action=VehicleAction.KEEP_LANE,
        risk_score=0.0,
    )


def test_vehicle_state_json_round_trip_preserves_fields() -> None:
    vehicle = _vehicle()
    restored = VehicleState.model_validate_json(vehicle.model_dump_json())
    assert restored == vehicle


def test_vehicle_state_rejects_unknown_fields() -> None:
    payload = _vehicle().model_dump()
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        VehicleState.model_validate(payload)


def test_websocket_envelope_requires_timezone_aware_sent_at() -> None:
    with pytest.raises(ValidationError):
        WebSocketEnvelope(
            type="world.snapshot",
            message_id="message-1",
            experiment_id=uuid4(),
            simulation_time_ms=0,
            sequence=0,
            sent_at=datetime(2026, 7, 15),
            payload={},
        )


def test_websocket_envelope_round_trip() -> None:
    message = WebSocketEnvelope(
        type="world.snapshot",
        message_id="message-1",
        experiment_id=uuid4(),
        simulation_time_ms=0,
        sequence=0,
        sent_at=datetime.now(timezone.utc),
        payload={"vehicles": []},
    )
    assert WebSocketEnvelope.model_validate_json(message.model_dump_json()) == message
