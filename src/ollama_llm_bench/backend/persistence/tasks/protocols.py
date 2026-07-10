"""The ``TasksStore`` contract owned by this module.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7.2.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import BenchmarkTask, RunId

__all__: list[str] = [
    "TasksStore",
]


class TasksStore(Protocol):
    """A run's frozen task snapshot and its keyword-term child rows.

    fast-synchronous: every method is a quick SQLite read/write under WAL and
    may be called from either the GUI thread or the dispatcher thread.
    """

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        """Insert a run's frozen task snapshot and its keyword-term child rows
        in one transaction.

        Raises:
            PersistenceError: The underlying write failed.
        """
        ...

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        """Return a run's frozen tasks in ascending ``task_order``, each
        assembled with its exact/semantic/forbidden term child rows.

        Raises:
            PersistenceError: The underlying read failed.
        """
        ...
