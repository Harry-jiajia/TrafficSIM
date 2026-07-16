"""Common immutable value objects."""

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Base model that rejects unknown fields and is immutable after validation."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)


class Vector3(StrictModel):
    x: float
    y: float
    z: float = 0.0
