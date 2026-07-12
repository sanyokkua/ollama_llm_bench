"""The one public type this module owns beyond its Protocol (08-E §18)."""

from enum import StrEnum


class CircuitState(StrEnum):
    """Per-provider breaker state (§6.2)."""

    CLOSED = "closed"
    TRIPPED = "tripped"
    PROBING = "probing"
