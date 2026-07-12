"""Mutable per-bucket bookkeeping — never crosses the module boundary (§6.1)."""

from dataclasses import dataclass
from enum import Enum, auto


class _BucketState(Enum):
    """The four-node state machine of §6.2. Never serialized — see AdaptiveTimeoutModelState
    in models.py for the public, serializable projection."""

    FRESH = auto()
    PROMOTED = auto()
    AT_MAX = auto()
    EXCLUDED = auto()


@dataclass(slots=True)
class _TimeoutState:
    """One (provider, model, role) bucket's bookkeeping (§6.1).

    ``last_queried_budget_ms`` is not part of the spec's public TimeoutState
    field table — it exists because ``record_timeout`` (unlike
    ``record_success``) takes no budget argument and must recover "the budget
    the caller last queried for this attempt" (§6.4) to decide whether the
    timeout was at the role's maximum.
    """

    state: _BucketState
    last_known_good_ms: int
    consecutive_max_timeouts: int
    last_queried_budget_ms: int
