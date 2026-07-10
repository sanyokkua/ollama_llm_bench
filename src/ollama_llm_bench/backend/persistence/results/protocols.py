"""The ``ResultsStore`` contract owned by this module.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7.3.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import BenchmarkResult, ResultId, ResultPatch, RunId

__all__: list[str] = [
    "ResultsStore",
]


class ResultsStore(Protocol):
    """Per-task results, the resume/retry sets, and the crash-recovery sweep.

    fast-synchronous: every method is a quick SQLite read/write under WAL and
    may be called from either the GUI thread or the dispatcher thread. During a
    run, run-domain writes are issued only by the dispatcher thread (DD-38/DD-41).
    """

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        """Insert the initial result rows for a run in one transaction.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...

    def update_result(self, result_id: ResultId, patch: ResultPatch) -> None:
        """Apply a partial update to one result. When the patch carries
        ``terms`` or ``attempts``, the child rows for that result are
        replaced wholesale. Identity columns are immutable.

        Raises:
            PersistenceError: The result does not exist, or the underlying
                write failed.
        """
        ...

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return every result of a run, each assembled with its term and
        attempt child rows.

        Raises:
            PersistenceError: The underlying read failed.
        """
        ...

    def list_resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return the results eligible to (re-)run on resume: rows in
        ``PENDING`` and rows in a retryable terminal-failure status.

        Raises:
            PersistenceError: The underlying read failed.
        """
        ...

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        """Full whole-task reset of the named results to
        ``ResultStatus.PENDING``, in one transaction, clearing the prior
        outcome and removing the term/attempt child rows. A row already in
        ``PENDING`` is left unchanged. Return the number of rows reset.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        """Reset the named results for retry from the failed stage (DD-66),
        in one transaction. Return the number of rows reset.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...

    def recover_in_flight_results(self) -> int:
        """Run the crash-recovery sweep: reset every result left in a
        non-terminal in-flight status back to ``PENDING`` and clear its
        in-flight columns and child rows. Return the number of rows reset.
        Idempotent across repeated calls.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...
