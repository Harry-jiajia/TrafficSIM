from __future__ import annotations

from uuid import UUID

import pytest

from trafficverse.domain.enums import AutomationLevel, VehicleAction
from trafficverse.domain.models import ActorSpawnResult, TrafficSnapshot, Vector3, VehicleState
from trafficverse.roi import (
    CoordinateTransformer,
    RegistrationConfig,
    RegistrationControlPoint,
    RegistrationTransform,
    RoiApplyResult,
    RoiDefinition,
    RoiSynchronizer,
)

EXPERIMENT_ID = UUID("00000000-0000-0000-0000-000000000705")


def _transformer() -> CoordinateTransformer:
    points = tuple(
        RegistrationControlPoint(traffic=point, carla=point)
        for point in (
            Vector3(x=0.0, y=0.0),
            Vector3(x=1.0, y=0.0),
            Vector3(x=0.0, y=1.0),
        )
    )
    return CoordinateTransformer(
        RegistrationConfig(
            source_coordinate_system="performance-fixture",
            transform=RegistrationTransform(axis_matrix=((1.0, 0.0), (0.0, 1.0))),
            control_points=points,
        ),
        max_error_m=0.01,
    )


def _vehicles(count: int) -> tuple[VehicleState, ...]:
    return tuple(
        VehicleState(
            experiment_id=EXPERIMENT_ID,
            vehicle_id=f"vehicle-{index:05d}",
            simulation_time_ms=0,
            sequence=0,
            automation_level=AutomationLevel.HUMAN,
            position=Vector3(x=float(index % 100), y=float(index // 100)),
            speed_mps=10.0,
            acceleration_mps2=0.0,
            heading_rad=0.0,
            lane_id="lane:scale",
            controller_id="fixture",
            action=VehicleAction.KEEP_LANE,
            risk_score=0.0,
        )
        for index in range(count)
    )


def _exercise(vehicle_count: int, ticks: int) -> None:
    vehicles = _vehicles(vehicle_count)
    synchronizer = RoiSynchronizer(
        RoiDefinition(
            radius_m=10_000.0,
            buffer_m=100.0,
            max_actors=vehicle_count,
            focus_x=0.0,
            focus_y=0.0,
        ),
        _transformer(),
    )
    first = synchronizer.plan(
        TrafficSnapshot(
            experiment_id=EXPERIMENT_ID,
            simulation_time_ms=50,
            sequence=1,
            vehicles=vehicles,
        )
    )
    synchronizer.commit(
        RoiApplyResult(
            plan=first,
            spawn_results=tuple(
                ActorSpawnResult(
                    vehicle_id=spec.vehicle_id,
                    success=True,
                    actor_id=index + 1,
                )
                for index, spec in enumerate(first.spawns)
            ),
        )
    )
    for sequence in range(2, ticks + 1):
        plan = synchronizer.plan(
            TrafficSnapshot(
                experiment_id=EXPERIMENT_ID,
                simulation_time_ms=sequence * 50,
                sequence=sequence,
                vehicles=vehicles,
            )
        )
        assert len(plan.actor_updates) == vehicle_count
        synchronizer.commit(RoiApplyResult(plan=plan))
    assert len(synchronizer.bindings) == vehicle_count

    cleanup = synchronizer.plan(
        TrafficSnapshot(
            experiment_id=EXPERIMENT_ID,
            simulation_time_ms=(ticks + 1) * 50,
            sequence=ticks + 1,
        )
    )
    synchronizer.commit(RoiApplyResult(plan=cleanup))
    assert synchronizer.bindings == ()
    assert synchronizer.actor_ids() == frozenset()


@pytest.mark.performance
def test_ten_thousand_vehicles_for_one_hundred_ticks() -> None:
    _exercise(10_000, 100)


@pytest.mark.performance
def test_one_thousand_vehicles_for_ten_thousand_ticks() -> None:
    _exercise(1_000, 10_000)
