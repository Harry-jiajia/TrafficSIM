"""Single traffic-to-CARLA rigid coordinate transformation boundary."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator, model_validator

from trafficverse.domain.models import StrictModel, Vector3


class RegistrationTransform(StrictModel):
    axis_matrix: tuple[tuple[float, float], tuple[float, float]]
    translation_m: Vector3 = Vector3(x=0.0, y=0.0, z=0.0)
    heading_sign: Literal[-1, 1] = 1
    heading_offset_rad: float = 0.0

    @field_validator("axis_matrix")
    @classmethod
    def matrix_must_be_rigid(
        cls, value: tuple[tuple[float, float], tuple[float, float]]
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        first, second = value
        dot = first[0] * second[0] + first[1] * second[1]
        determinant = first[0] * second[1] - first[1] * second[0]
        if not (
            math.isclose(math.hypot(*first), 1.0, abs_tol=1e-9)
            and math.isclose(math.hypot(*second), 1.0, abs_tol=1e-9)
            and math.isclose(dot, 0.0, abs_tol=1e-9)
            and math.isclose(abs(determinant), 1.0, abs_tol=1e-9)
        ):
            raise ValueError("registration axis_matrix must be orthonormal")
        return value

    @model_validator(mode="after")
    def heading_transform_must_match_axis_matrix(self) -> RegistrationTransform:
        matrix = self.axis_matrix
        mapped_zero = math.atan2(matrix[1][0], matrix[0][0])
        mapped_quarter = math.atan2(matrix[1][1], matrix[0][1])
        expected_zero = self.heading_offset_rad
        expected_quarter = self.heading_sign * math.pi / 2 + self.heading_offset_rad
        for actual, expected in (
            (mapped_zero, expected_zero),
            (mapped_quarter, expected_quarter),
        ):
            difference = (actual - expected + math.pi) % (2 * math.pi) - math.pi
            if not math.isclose(difference, 0.0, abs_tol=1e-9):
                raise ValueError("heading transform must match registration axis_matrix")
        return self


class RegistrationControlPoint(StrictModel):
    traffic: Vector3
    carla: Vector3


class RegistrationConfig(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    source_coordinate_system: str = Field(min_length=1)
    target_coordinate_system: Literal["CARLA"] = "CARLA"
    transform: RegistrationTransform
    control_points: tuple[RegistrationControlPoint, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def control_points_must_be_non_collinear(self) -> RegistrationConfig:
        points = [point.traffic for point in self.control_points]
        origin = points[0]
        if not any(
            abs(
                (first.x - origin.x) * (second.y - origin.y)
                - (first.y - origin.y) * (second.x - origin.x)
            )
            > 1e-9
            for index, first in enumerate(points[1:], start=1)
            for second in points[index + 1 :]
        ):
            raise ValueError("registration control points must be non-collinear")
        return self


class CoordinateTransformer:
    def __init__(self, config: RegistrationConfig, *, max_error_m: float) -> None:
        if max_error_m <= 0:
            raise ValueError("max registration error must be positive")
        self._config = config
        self._max_error_m = max_error_m
        error = self.maximum_control_point_error_m
        if error > max_error_m:
            raise ValueError(
                f"registration error {error:.6f} m exceeds threshold {max_error_m:.6f} m"
            )

    @classmethod
    def from_yaml(cls, path: Path, *, max_error_m: float) -> CoordinateTransformer:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(RegistrationConfig.model_validate(payload), max_error_m=max_error_m)

    def transform_position(self, position: Vector3) -> Vector3:
        matrix = self._config.transform.axis_matrix
        translation = self._config.transform.translation_m
        return Vector3(
            x=matrix[0][0] * position.x + matrix[0][1] * position.y + translation.x,
            y=matrix[1][0] * position.x + matrix[1][1] * position.y + translation.y,
            z=position.z + translation.z,
        )

    def transform_heading(self, heading_rad: float) -> float:
        transformed = (
            self._config.transform.heading_sign * heading_rad
            + self._config.transform.heading_offset_rad
        )
        return (transformed + math.pi) % (2.0 * math.pi) - math.pi

    @property
    def maximum_control_point_error_m(self) -> float:
        return max(
            math.dist(
                (
                    self.transform_position(point.traffic).x,
                    self.transform_position(point.traffic).y,
                    self.transform_position(point.traffic).z,
                ),
                (point.carla.x, point.carla.y, point.carla.z),
            )
            for point in self._config.control_points
        )
