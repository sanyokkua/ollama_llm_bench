"""Gateways for ``ui/common_dialogs/`` -- Run Summary, Rename Run (STORY-055/056),
and Resume Summary / Retry Selection (STORY-057).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/run_summary_dialog.md``
§8 (preflight re-check), §12 (Start Effects); ``resume_summary_dialog.md`` §5-§7,
§11; ``retry_selection_dialog.md`` §7, §13; ``08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.3. Each Gateway is declared locally, scoped to exactly its own dialog's backend
calls -- never importing another sibling UI module's own Gateway (that module's
Gateway is its own swap point, not a shared one). A concrete adapter satisfying
multiple Gateway Protocols with one class, or several thin ones, is Phase 11's
decision (compose.py), not this story's -- e.g. ``NewBenchmarkGateway`` already
exposes both ``RunSummaryGateway`` methods and so satisfies that Protocol
structurally, with no adapter shim, exactly like ``ModeVisibilityPolicy``'s
structural-satisfaction pattern (STORY-054); ``ResumeGateway``
(``ui.resume_benchmark.protocols``) likewise structurally satisfies both
``ResumeSummaryGateway`` and ``RetrySelectionGateway`` below.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    ResultId,
    RunId,
    RunStartRequest,
)
from ollama_llm_bench.backend.run_drift import DriftWarning

__all__: list[str] = [
    "RenameRunGateway",
    "ResumeSummaryGateway",
    "RetrySelectionGateway",
    "RunSummaryGateway",
]


class RunSummaryGateway(Protocol):
    """Adapter gateway for the Run Summary dialog (D-R-06)."""

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        """Return the current readiness snapshot.

        fast-synchronous. Re-checked on every dialog open (§8).
        """
        ...

    def start_run(self, request: RunStartRequest) -> RunId:
        """Start a benchmark run from the assembled request; returns the run id.

        fast-synchronous (enqueues to the dispatcher thread and returns). §12
        Start Effects.
        """
        ...


class RenameRunGateway(Protocol):
    """Adapter gateway for the Rename Run dialog (D-R-06).

    Shares ``list_runs``/``rename_run`` verbatim with ``ResumeGateway``
    (08-E §7b.3) by design -- a concrete adapter satisfies both Protocols
    structurally with one class, per the structural-satisfaction pattern
    already used elsewhere in this codebase.
    """

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        """Return every run header -- used for the V-5 name-uniqueness check."""
        ...

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        """Persist the new name (or clear it, for the default-intent case)."""
        ...


class ResumeSummaryGateway(Protocol):
    """Adapter gateway for the Resume Summary dialog (D-R-06).

    Shares every method name verbatim with ``ResumeGateway``
    (``ui.resume_benchmark.protocols``, 08-E §7b.3) by design -- a concrete
    adapter satisfies this Protocol structurally with no shim, exactly like
    ``RenameRunGateway`` above.
    """

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        """Load the run under review."""
        ...

    def resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return the results eligible for the inline Tasks-to-resume picker."""
        ...

    def detect_drift(self, run_id: RunId) -> tuple[DriftWarning, ...]:
        """Run the Run Drift Detector fresh; never raises (see ResumeGateway)."""
        ...

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        """Full whole-task reset of the checked rows to PENDING; return the count reset."""
        ...

    def resume_run(self, run_id: RunId) -> None:
        """Resume the run against its frozen settings_snapshot."""
        ...


class RetrySelectionGateway(Protocol):
    """Adapter gateway for the Retry Selection dialog (D-R-06).

    Shares every method name verbatim with ``ResumeGateway`` by design.
    """

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return every result row of the run, for the checkable table."""
        ...

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        """Stage-preserving retry reset (DD-66); return the count reset."""
        ...

    def resume_run(self, run_id: RunId) -> None:
        """Resume the run against its frozen settings_snapshot."""
        ...
