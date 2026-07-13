"""The single backend run-engine contract (08-E §11)."""

from typing import Protocol

from ollama_llm_bench.backend.domain.models import BenchmarkRun, RunId, RunStartRequest


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
