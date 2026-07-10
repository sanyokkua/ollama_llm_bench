"""The ``RunsStore`` contract owned by this module.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7.1.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import BenchmarkRun, RunId, RunStatusPatch

__all__: list[str] = [
    "RunsStore",
]


class RunsStore(Protocol):
    """Run headers and their three frozen snapshot child tables.

    fast-synchronous: every method is a quick SQLite read/write under WAL and
    may be called from either the GUI thread or the dispatcher thread. During a
    run, run-domain writes are issued only by the dispatcher thread (DD-38/DD-41).
    """

    def create_run(self, run: BenchmarkRun) -> RunId:
        """Insert a run header and its three frozen snapshot child tables
        (models, providers, settings) in one transaction. Return the new run id.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        """Load one run, fully assembled with its snapshot collections.

        Raises:
            PersistenceError: The run does not exist, or the underlying read
                failed.
        """
        ...

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        """Return every run header, newest first.

        Raises:
            PersistenceError: The underlying read failed.
        """
        ...

    def update_run_status(self, run_id: RunId, patch: RunStatusPatch) -> None:
        """Apply a partial update to a run header (status, counters, analysis,
        timestamps). Identity columns and the snapshot tables are immutable.

        Raises:
            PersistenceError: The run does not exist, or the underlying write
                failed.
        """
        ...

    def rename_run(self, run_id: RunId, run_name: str | None) -> None:
        """Set or clear the user-facing run name. ``None`` restores the
        generated name.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...

    def delete_run(self, run_id: RunId) -> None:
        """Delete a run; the cascade removes every dependent row.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...
