"""DD-42 outcome-matrix resolution from a single atomic CancellationToken snapshot."""

import msgspec

from ollama_llm_bench.backend.domain.models import CancelLevel, CancelReason, RunStatus


class HaltOutcome(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The persisted-status decision derived from one token.snapshot() (DD-42)."""

    persisted_status: RunStatus | None
    parked_paused: bool


def resolve_halt_outcome(
    *, level: CancelLevel, reason: CancelReason | None, all_rows_completed: bool
) -> HaltOutcome:
    """Resolve the DD-42 outcome matrix for exactly one halt.

    Args:
        level: The token's cancellation level at the moment of halt.
        reason: The token's cancellation reason at the moment of halt.
        all_rows_completed: Whether every result row reached COMPLETED (only
            meaningful when level is NONE).

    Returns:
        The persisted-status decision; `persisted_status=None` means the run
        stays `INCOMPLETE` with no terminal write.
    """
    if level is CancelLevel.NONE:
        status = RunStatus.COMPLETED if all_rows_completed else RunStatus.STOPPED
        return HaltOutcome(persisted_status=status, parked_paused=False)
    if level is CancelLevel.SOFT:
        return HaltOutcome(persisted_status=None, parked_paused=True)
    # level is CancelLevel.HARD
    if reason is CancelReason.USER_STOP:
        return HaltOutcome(persisted_status=RunStatus.STOPPED, parked_paused=False)
    return HaltOutcome(persisted_status=None, parked_paused=False)  # APP_SHUTDOWN
