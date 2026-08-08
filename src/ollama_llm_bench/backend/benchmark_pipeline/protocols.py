"""The single backend run-engine contract (08-E §11)."""

from typing import Protocol

from ollama_llm_bench.backend.domain.models import (
    BenchmarkRun,
    BenchmarkTask,
    RunId,
    RunStartRequest,
)


class RunTaskStager(Protocol):
    """Expand a `RunStartRequest` into the frozen task rows a run will execute.

    Pure: it builds tasks and persists nothing, so it needs no `run_id` and can
    be called before the run header exists. That ordering is what lets
    `BenchmarkFlowApi.start` know a run's real `total_tasks` at creation time.
    """

    def build(self, request: RunStartRequest, /) -> tuple[BenchmarkTask, ...]:
        """Return the tasks `request` expands to, in execution order.

        A `SYNTHETIC` request expands its `performance_config` grid; a `TASKS`/
        `GRADED` request loads every path in `task_paths`. Fast-synchronous, but
        the file-loading path performs blocking reads.

        Args:
            request: The run-start request assembled by the New Benchmark widget.

        Returns:
            The run's frozen tasks, each carrying its position as `task_order`.
            Empty when the request names no tasks at all.

        Raises:
            TaskFileError: A path in `request.task_paths` could not be read or
                parsed at all. `BenchmarkFlowApi.start` catches this and
                surfaces it as a rejected run start; it never reaches `start`'s
                own caller.
        """
        ...


class BenchmarkFlowApi(Protocol):
    """Controls the lifecycle of a single benchmark run. Never raises to the caller."""

    def start(self, request: RunStartRequest) -> RunId:
        """Create a run, hand it to the dispatcher thread, and return its id promptly.

        fast-synchronous on the GUI thread. Admission is the gate (SPEC-036):
        the first step is InferenceActivityStore.try_acquire(BENCHMARK_RUN); a
        failed acquire makes no new run, writes nothing, and is surfaced as a
        rejected RunStatus.FAILED record — never raised.
        """
        ...

    def resume(self, run_id: RunId) -> None:
        """Resume an INCOMPLETE run's PENDING/retryable rows from where crash recovery left them.

        fast-synchronous on the GUI thread. Same gate-admission-first rule as
        start(); a failed acquire is a no-op (resets no rows, enqueues nothing).
        """
        ...

    def pause(self) -> None:
        """Request a cooperative pause at the next safe checkpoint. No-op when idle or already paused."""
        ...

    def resume_paused(self) -> None:
        """Resume execution after pause(). No-op when idle or not paused."""
        ...

    def stop(self) -> None:
        """Request a hard-cancel stop (CancelReason.USER_STOP). No-op when idle."""
        ...

    def shutdown(self, timeout_ms: int) -> None:
        """Stop the active run gracefully on quit; wait up to timeout_ms then return."""
        ...

    def is_running(self) -> bool:
        """Whether a run is currently executing (including the paused state)."""
        ...

    def current_run(self) -> BenchmarkRun | None:
        """The run currently being executed, or None when idle."""
        ...
