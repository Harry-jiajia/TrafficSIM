"""Stable application-facing error types."""

from collections.abc import Mapping

from trafficverse.domain.enums import ErrorCode


class TrafficVerseError(Exception):
    """Base error carrying a stable machine-readable code."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


class ConfigurationError(TrafficVerseError):
    """Configuration cannot be loaded or validated."""


class InvalidStateTransitionError(TrafficVerseError):
    """Requested experiment state transition is not allowed."""


class VersionMismatchError(TrafficVerseError):
    """Runtime component version does not match the selected baseline."""
