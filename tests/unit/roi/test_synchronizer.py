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

EXPERIMENT_ID = UUID("00000000-0000-0000-0000-000000000007")


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
            source_coordinate_system="fixture",
            transform=RegistrationTransform(axis_matrix=((1.0, 0.0), (0.0, 1.0))),
            control_points=points,
        ),
        max_error_m=0.01,
    )


def _vehicle(vehicle_id: str, distance_m: float) -> VehicleState:
    return VehicleState(
        experiment_id=EXPERIMENT_ID,
        vehicle_id=vehicle_id,
        simulation_time_ms=0,
        sequence=0,
        automation_level=AutomationLevel.HUMAN,
        position=Vector3(x=distance_m, y=0.0),
        speed_mps=1.0,
        acceleration_mps2=0.0,
        heading_rad=0.0,
        lane_id="lane:1",
        controller_id="fixture",
        action=VehicleAction.KEEP_LANE,
        risk_score=0.0,
    )


def _snapshot(sequence: int, *vehicles: VehicleState) -> TrafficSnapshot:
    return TrafficSnapshot(
        experiment_id=EXPERIMENT_ID,
        simulation_time_ms=sequence * 50,
        sequence=sequence,
        vehicles=vehicles,
    )


def _synchronizer(*, max_actors: int = 10) -> RoiSynchronizer:
    return RoiSynchronizer(
        RoiDefinition(
            radius_m=1000.0,
            buffer_m=200.0,
            max_actors=max_actors,
            focus_x=0.0,
            focus_y=0.0,
        ),
        _transformer(),
    )


def _commit_success(sync: RoiSynchronizer, plan: object, actor_start: int = 100) -> None:
    from trafficverse.roi import RoiApplyPlan

    assert isinstance(plan, RoiApplyPlan)
    results = tuple(
        ActorSpawnResult(vehicle_id=spec.vehicle_id, success=True, actor_id=actor_start + index)
        for index, spec in enumerate(plan.spawns)
    )
    sync.commit(RoiApplyResult(plan=plan, spawn_results=results))


def test_core_and_buffer_hysteresis_spawns_and_destroys_exactly_once() -> None:
    sync = _synchronizer()
    spawn_count = 0
    destroy_count = 0

    for sequence, distance in enumerate((999.0, 1001.0, 1199.0, 1201.0), start=1):
        plan = sync.plan(_snapshot(sequence, _vehicle("v1", distance)))
        spawn_count += len(plan.spawns)
        destroy_count += len(plan.destroy_actor_ids)
        assert not ({item.vehicle_id for item in plan.spawns} & set(plan.destroy_vehicle_ids))
        _commit_success(sync, plan)

    assert spawn_count == 1
    assert destroy_count == 1
    assert sync.bindings == ()


def test_disappeared_vehicle_is_destroyed_once() -> None:
    sync = _synchronizer()
    first = sync.plan(_snapshot(1, _vehicle("v1", 10.0)))
    _commit_success(sync, first)

    destroy = sync.plan(_snapshot(2))
    assert destroy.destroy_vehicle_ids == ("v1",)
    _commit_success(sync, destroy)
    assert sync.plan(_snapshot(3)).destroy_actor_ids == ()


def test_missing_actor_mapping_is_removed_and_respawned_when_still_inside_roi() -> None:
    sync = _synchronizer()
    first = sync.plan(_snapshot(1, _vehicle("v1", 10.0)))
    _commit_success(sync, first, actor_start=77)

    sync.report_missing_actor_ids(frozenset({77}))
    replacement = sync.plan(_snapshot(2, _vehicle("v1", 10.0)))

    assert tuple(spec.vehicle_id for spec in replacement.spawns) == ("v1",)
    assert replacement.destroy_actor_ids == ()


def test_partial_spawn_failure_only_commits_success_and_retries_failed_vehicle() -> None:
    sync = _synchronizer()
    plan = sync.plan(_snapshot(1, _vehicle("v1", 10.0), _vehicle("v2", 20.0)))
    sync.commit(
        RoiApplyResult(
            plan=plan,
            spawn_results=(
                ActorSpawnResult(vehicle_id="v1", success=True, actor_id=1),
                ActorSpawnResult(vehicle_id="v2", success=False, error="collision"),
            ),
        )
    )

    assert tuple(binding.vehicle_id for binding in sync.bindings) == ("v1",)
    retry = sync.plan(_snapshot(2, _vehicle("v1", 10.0), _vehicle("v2", 20.0)))
    assert tuple(spec.vehicle_id for spec in retry.spawns) == ("v2",)


def test_duplicate_actor_result_is_rejected_without_partial_binding() -> None:
    sync = _synchronizer()
    plan = sync.plan(_snapshot(1, _vehicle("v1", 10.0), _vehicle("v2", 20.0)))

    with pytest.raises(ValueError, match="duplicate actor"):
        sync.commit(
            RoiApplyResult(
                plan=plan,
                spawn_results=(
                    ActorSpawnResult(vehicle_id="v1", success=True, actor_id=1),
                    ActorSpawnResult(vehicle_id="v2", success=True, actor_id=1),
                ),
            )
        )
    assert sync.bindings == ()


def test_actor_limit_prioritizes_focus_and_nearest_vehicles() -> None:
    sync = RoiSynchronizer(
        RoiDefinition(
            radius_m=1000.0,
            buffer_m=200.0,
            max_actors=2,
            focus_x=0.0,
            focus_y=0.0,
            priority_vehicle_ids=frozenset({"priority"}),
        ),
        _transformer(),
    )

    plan = sync.plan(
        _snapshot(
            1,
            _vehicle("near", 1.0),
            _vehicle("middle", 2.0),
            _vehicle("priority", 900.0),
        )
    )

    assert tuple(item.vehicle_id for item in plan.spawns) == ("priority", "near")
    assert plan.degraded_vehicle_ids == ("middle",)


def test_follow_vehicle_focus_moves_roi() -> None:
    sync = RoiSynchronizer(
        RoiDefinition(
            radius_m=10.0,
            buffer_m=2.0,
            max_actors=2,
            focus_vehicle_id="ego",
        ),
        _transformer(),
    )

    plan = sync.plan(_snapshot(1, _vehicle("ego", 100.0), _vehicle("near", 109.0)))

    assert {item.vehicle_id for item in plan.spawns} == {"ego", "near"}
