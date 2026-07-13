"""Proves: STORY-029-AC-5"""

import pytest

from ollama_llm_bench.backend.benchmark_pipeline._internal.outcome import (
    HaltOutcome,
    resolve_halt_outcome,
)
from ollama_llm_bench.backend.domain.models import CancelLevel, CancelReason, RunStatus


@pytest.mark.parametrize(
    ("level", "reason", "all_rows_completed", "expected"),
    [
        (
            CancelLevel.NONE,
            None,
            True,
            HaltOutcome(persisted_status=RunStatus.COMPLETED, parked_paused=False),
        ),
        (
            CancelLevel.NONE,
            None,
            False,
            HaltOutcome(persisted_status=RunStatus.STOPPED, parked_paused=False),
        ),
        (
            CancelLevel.SOFT,
            CancelReason.USER_PAUSE,
            False,
            HaltOutcome(persisted_status=None, parked_paused=True),
        ),
        (
            CancelLevel.SOFT,
            CancelReason.AUTO_PAUSE,
            False,
            HaltOutcome(persisted_status=None, parked_paused=True),
        ),
        (
            CancelLevel.HARD,
            CancelReason.USER_STOP,
            False,
            HaltOutcome(persisted_status=RunStatus.STOPPED, parked_paused=False),
        ),
        (
            CancelLevel.HARD,
            CancelReason.APP_SHUTDOWN,
            False,
            HaltOutcome(persisted_status=None, parked_paused=False),
        ),
    ],
)
def test_dd42_outcome_matrix_from_single_snapshot(
    level: CancelLevel,
    reason: CancelReason | None,
    all_rows_completed: bool,  # noqa: FBT001  # pytest.mark.parametrize test fixture
    expected: HaltOutcome,
) -> None:
    """Proves: STORY-029-AC-5

    Table-driven over the exact DD-42 outcome matrix from a single
    (CancelLevel, CancelReason) snapshot.
    """
    result = resolve_halt_outcome(level=level, reason=reason, all_rows_completed=all_rows_completed)
    assert result == expected
