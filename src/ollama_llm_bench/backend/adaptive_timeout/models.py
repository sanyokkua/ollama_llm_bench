"""The one public type this module owns beyond its Protocol (08-E §17)."""

from enum import StrEnum


class AdaptiveTimeoutModelState(StrEnum):
    """Stability state of a (provider, model, role) bucket, surfaced via ``model_state``."""

    OK = "ok"
    WARN = "warn"
    EXCLUDED = "excluded"
