from __future__ import annotations

import math
from pathlib import Path

import pytest

from trafficverse.domain.models import Vector3
from trafficverse.roi import (
    CoordinateTransformer,
    RegistrationConfig,
    RegistrationControlPoint,
    RegistrationTransform,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _config(*, bad_error_m: float = 0.0) -> RegistrationConfig:
    return RegistrationConfig(
        source_coordinate_system="fixture",
        transform=RegistrationTransform(
            axis_matrix=((0.0, 1.0), (1.0, 0.0)),
            translation_m=Vector3(x=10.0, y=20.0, z=1.0),
            heading_sign=-1,
            heading_offset_rad=math.pi / 2,
        ),
        control_points=(
            RegistrationControlPoint(
                traffic=Vector3(x=0.0, y=0.0, z=0.0),
                carla=Vector3(x=10.0 + bad_error_m, y=20.0, z=1.0),
            ),
            RegistrationControlPoint(
                traffic=Vector3(x=10.0, y=0.0, z=0.0),
                carla=Vector3(x=10.0, y=30.0, z=1.0),
            ),
            RegistrationControlPoint(
                traffic=Vector3(x=0.0, y=10.0, z=0.0),
                carla=Vector3(x=20.0, y=20.0, z=1.0),
            ),
        ),
    )


def test_position_axis_heading_and_wrap_are_centralized() -> None:
    transformer = CoordinateTransformer(_config(), max_error_m=0.01)

    assert transformer.transform_position(Vector3(x=3.0, y=4.0, z=2.0)) == Vector3(
        x=14.0, y=23.0, z=3.0
    )
    assert transformer.transform_heading(0.0) == pytest.approx(math.pi / 2)
    assert transformer.transform_heading(-math.pi) == pytest.approx(-math.pi / 2)
    assert transformer.maximum_control_point_error_m == 0.0


def test_registration_above_threshold_refuses_startup() -> None:
    with pytest.raises(ValueError, match="exceeds threshold"):
        CoordinateTransformer(_config(bad_error_m=0.6), max_error_m=0.5)


def test_town04_registration_has_three_control_points_and_valid_checksum_asset() -> None:
    transformer = CoordinateTransformer.from_yaml(
        REPOSITORY_ROOT / "configs/maps/town04/registration.yaml",
        max_error_m=0.001,
    )

    assert transformer.maximum_control_point_error_m == 0.0
    assert transformer.transform_position(Vector3(x=7.0, y=-4.0, z=0.5)) == Vector3(
        x=7.0, y=-4.0, z=0.5
    )
