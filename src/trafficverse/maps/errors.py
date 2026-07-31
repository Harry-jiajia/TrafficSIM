"""Stable map compilation failures."""


class MapCompileError(ValueError):
    """OpenDRIVE input cannot be represented by the frozen MVP schema."""


class SumoPackageError(ValueError):
    """A SUMO scenario package is incomplete, unsafe, or structurally invalid."""
