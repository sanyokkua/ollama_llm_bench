"""``ResumeGateway`` (D-R-06) -- the Resume Benchmark widget's own adapter gateway.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.3. Declared locally, scoped to exactly this widget's backend calls -- wraps
``RunsStore``, ``ResultsStore``, ``TasksStore``, ``ReadinessService`` (drift
refresh), ``SettingsService`` (sort persistence), and the resume command.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ResultId,
    ResultPatch,
    RunId,
    RunStatusPatch,
)

__all__: list[str] = ["ResumeGateway"]


class ResumeGateway(Protocol):
    """Adapter gateway for the Resume Benchmark widget (D-R-06)."""

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        """Return every run header, newest first, for the run table."""
        ...

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        """Load one fully-assembled run (for Clone / detail reads)."""
        ...

    def create_run(self, run: BenchmarkRun) -> RunId:
        """Create a run header + snapshots (the Clone-as-new-retry-run use case)."""
        ...

    def update_run_status(self, run_id: RunId, patch: RunStatusPatch) -> None:
        """Apply a run-header status/counter patch."""
        ...

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        """Set or clear a run's user-facing name."""
        ...

    def delete_run(self, run_id: RunId) -> None:
        """Delete a run and its dependent rows."""
        ...

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return a run's results (for counts / Clone)."""
        ...

    def resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return the results eligible to (re-)run on resume."""
        ...

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        """Full whole-task reset of the named results to PENDING; return the count reset."""
        ...

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        """Stage-preserving retry reset (DD-66); return the count reset."""
        ...

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        """Insert initial result rows (Clone-as-new-retry-run)."""
        ...

    def update_result(self, result_id: ResultId, patch: ResultPatch) -> None:
        """Apply a partial update to one result row."""
        ...

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        """Return a run's frozen tasks (Clone)."""
        ...

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        """Insert a run's frozen task snapshot (Clone-as-new-retry-run)."""
        ...

    def refresh_readiness(self) -> AppReadinessSnapshot:
        """Refresh the readiness snapshot before the Run Drift Detector runs."""
        ...

    def get_sort_setting(self) -> tuple[str, bool]:
        """Read the persisted sort column and descending flag."""
        ...

    def set_sort_setting(self, column: str, descending: bool) -> None:  # noqa: FBT001  # mirrors 08-E §7b.3 verbatim
        """Persist the sort column and direction."""
        ...

    def resume_run(self, run_id: RunId) -> None:
        """Resume an INCOMPLETE run from where crash recovery left it."""
        ...

    def is_run_active(self) -> bool:
        """Whether a run is currently executing (for the per-row ``is_executing`` flag)."""
        ...

    def active_run_id(self) -> RunId | None:
        """The id of the currently executing run, or ``None`` when idle."""
        ...
