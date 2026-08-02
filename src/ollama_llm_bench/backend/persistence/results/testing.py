"""A deterministic in-memory fake ``ResultsStore`` for downstream module tests.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/01_SERVICE_INVENTORY.md``
§6 (test-double convention) — every contract service is faked in its own package's
``testing.py``, honouring the same contract as the real ``SqliteResultsStore``.
"""

from collections.abc import Iterable
from typing import Final

import msgspec

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    ResultId,
    ResultPatch,
    ResultStatus,
    RunId,
)

__all__: list[str] = ["FakeResultsStore"]

# The retryable terminal-failure statuses (mirrors `SqliteResultsStore`'s
# `_RETRYABLE_FAILURE_STATUSES` — a row in one of these is eligible to resume).
_RETRYABLE_FAILURE_STATUSES: Final[tuple[ResultStatus, ...]] = (
    ResultStatus.FAILED_INFERENCE,
    ResultStatus.FAILED_PROVIDER,
    ResultStatus.FAILED_TIMEOUT,
    ResultStatus.FAILED_JUDGE_TIMEOUT,
    ResultStatus.ERRORED,
)

# The non-terminal in-flight statuses the crash-recovery sweep resets to
# PENDING (mirrors `SqliteResultsStore`'s `_IN_FLIGHT_STATUSES`).
_IN_FLIGHT_STATUSES: Final[tuple[ResultStatus, ...]] = (
    ResultStatus.RUNNING_INFERENCE,
    ResultStatus.AWAITING_KEYWORD_CHECK,
    ResultStatus.AWAITING_COSINE_CHECK,
    ResultStatus.AWAITING_JUDGE_CHECK,
)


class FakeResultsStore:
    """An in-memory, deterministic double honouring the ``ResultsStore`` contract.

    No real database, no transactions, no thread-safety — a plain test double
    backed by a ``dict[ResultId, BenchmarkResult]``, seeded directly via the
    constructor or populated through ordinary ``create_results`` calls.
    """

    def __init__(self, *, initial: Iterable[BenchmarkResult] = ()) -> None:
        self._rows: dict[ResultId, BenchmarkResult] = {row.result_id: row for row in initial}

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        """Insert the initial result rows for a run, keyed by ``result_id``."""
        for result in results:
            self._rows[result.result_id] = result

    def update_result(self, result_id: ResultId, patch: ResultPatch) -> None:
        """Merge every non-``None`` field of ``patch`` onto the stored row."""
        current = self._rows[result_id]
        changes = {
            field: getattr(patch, field)
            for field in patch.__struct_fields__
            if getattr(patch, field) is not None
        }
        self._rows[result_id] = msgspec.structs.replace(current, **changes)

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return every stored row for ``run_id``, in insertion order."""
        return tuple(row for row in self._rows.values() if row.run_id == run_id)

    def list_resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return ``run_id``'s rows in ``PENDING`` or a retryable failure status."""
        return tuple(
            row
            for row in self._rows.values()
            if row.run_id == run_id
            and (row.status is ResultStatus.PENDING or row.status in _RETRYABLE_FAILURE_STATUSES)
        )

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        """Reset each named row to ``PENDING``; return the count actually changed."""
        return self._reset_to_pending(result_ids)

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        """Reset each named row to ``PENDING``; return the count actually changed.

        A full reset is sufficient for this fake — stage-preserving retry
        reset (DD-66) is out of scope for the stories this fake currently
        supports.
        """
        return self._reset_to_pending(result_ids)

    def recover_in_flight_results(self) -> int:
        """Reset every row in a non-terminal in-flight status back to ``PENDING``, clearing
        every outcome/in-flight column and child row (mirrors `SqliteResultsStore`'s
        `_FULL_RESET_SET_CLAUSE`)."""
        changed = 0
        for result_id, row in self._rows.items():
            if row.status not in _IN_FLIGHT_STATUSES:
                continue
            self._rows[result_id] = msgspec.structs.replace(
                row,
                status=ResultStatus.PENDING,
                verdict=None,
                started_at=None,
                finished_at=None,
                system_prompt_sent=None,
                user_prompt_sent=None,
                raw_response=None,
                sanitized_response=None,
                has_thinking_block=False,
                response_char_length=None,
                total_time_ms=None,
                ttft_ms=None,
                prompt_tokens=None,
                completion_tokens=None,
                tokens_per_second=None,
                sanity_check_passed=None,
                keyword_verdict=None,
                cosine_similarity=None,
                cosine_verdict=None,
                judge_verdict=None,
                judge_reasoning=None,
                judge_time_ms=None,
                judge_completion_tokens=None,
                resolution_layer=None,
                error_kind=None,
                error_message=None,
                terms=(),
                attempts=(),
            )
            changed += 1
        return changed

    def _reset_to_pending(self, result_ids: tuple[ResultId, ...]) -> int:
        """Set each named row's status to ``PENDING``; return the count changed."""
        changed = 0
        for result_id in result_ids:
            row = self._rows[result_id]
            if row.status is ResultStatus.PENDING:
                continue
            self._rows[result_id] = msgspec.structs.replace(row, status=ResultStatus.PENDING)
            changed += 1
        return changed
