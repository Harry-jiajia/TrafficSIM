"""ROI synchronization, registration, and signal binding."""

from trafficverse.roi.coordinate_transformer import (
    CoordinateTransformer,
    RegistrationConfig,
    RegistrationControlPoint,
    RegistrationTransform,
)
from trafficverse.roi.models import (
    RoiApplyPlan,
    RoiApplyResult,
    RoiDefinition,
    VehicleActorTransform,
    VehicleBinding,
    VehicleRenderSpec,
)
from trafficverse.roi.signal_synchronizer import SignalSynchronizer
from trafficverse.roi.synchronizer import RoiSynchronizer

__all__ = [
    "CoordinateTransformer",
    "RegistrationConfig",
    "RegistrationControlPoint",
    "RegistrationTransform",
    "RoiApplyPlan",
    "RoiApplyResult",
    "RoiDefinition",
    "RoiSynchronizer",
    "SignalSynchronizer",
    "VehicleActorTransform",
    "VehicleBinding",
    "VehicleRenderSpec",
]
