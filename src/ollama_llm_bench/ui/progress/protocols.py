"""``ProgressGateway`` (D-R-06) -- the Progress widget's own adapter gateway.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.4 (the base surface, declared verbatim below) plus two locally-added
extensions this story's grounding pass identified as real gaps:

- ``list_runs()`` -- 08-E §7b.4 carries no such method, but the header's rename
  pencil opens the already-built ``make_rename_run_dialog(...)``
  (``ui.common_dialogs.api``), whose ``RenameRunGateway`` Protocol requires both
  ``list_runs()`` and ``rename_run(...)``. This mirrors the "structurally
  satisfies a sibling dialog's Gateway" pattern already documented in
  ``ui/common_dialogs/protocols.py``'s module docstring (``ResumeGateway``
  structurally satisfies ``ResumeSummaryGateway``/``RetrySelectionGateway`` the
  same way).
- ``is_run_active()`` -- naming precedent: ``MainWindowGateway.is_run_active()``
  and ``ResumeGateway.is_run_active()``. Needed by the SPEC-098 bounded
  reconciliation timer (``description.md`` §10), which reconciles a lost
  terminal event via ``is_run_active()`` plus ``run_header(run_id).status``.

Both additions are pure extensions of this module's own Protocol -- no other
module's file changes.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import BenchmarkResult, BenchmarkRun, RunId, SettingKey

__all__: list[str] = ["ProgressGateway"]


class ProgressGateway(Protocol):
    """Adapter gateway for the Progress widget (D-R-06)."""

    def pause_run(self) -> None:
        """Request a cooperative pause of the active run.

        fast-synchronous -- routes through the run's ``CancellationToken``
        (soft cancel) and returns promptly; the pipeline parks asynchronously
        and reports back via ``_run_paused``.
        """
        ...

    def resume_run(self) -> None:
        """Resume execution after a pause.

        fast-synchronous -- enqueues the resume command to the dispatcher
        thread and returns; the pipeline restarts asynchronously and reports
        back via ``_run_resumed``.
        """
        ...

    def stop_run(self, reason: str | None = None) -> None:
        """Request a cooperative stop of the active run.

        fast-synchronous -- routes through the run's ``CancellationToken``
        (hard cancel) and returns promptly; termination is reported back via
        ``_run_stopped``.
        """
        ...

    def run_metadata(self, run_id: RunId) -> BenchmarkRun:
        """Read the active run's metadata from the run registry.

        fast-synchronous -- a single-row store read.
        """
        ...

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        """Set or clear the active run's user-facing name (the inline pencil).

        fast-synchronous -- a single-row store write; emits ``_run_renamed``.
        """
        ...

    def run_header(self, run_id: RunId) -> BenchmarkRun:
        """Read a run header -- elapsed time and the terminal run summary.

        fast-synchronous -- a single-row store read.
        """
        ...

    def task_counters(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Read per-task result rows for the run-progress counters / current task.

        fast-synchronous -- a bounded store read.
        """
        ...

    def load_past_log(self, run_id: RunId) -> str:
        """Load the saved run-log of a past run for replay.

        blocking -- reads a file from disk; call only from a ``TaskRunner``
        worker, never the GUI thread.
        """
        ...

    def get_setting(self, key: SettingKey) -> str | None:
        """Read ``ui.run_log_verbosity`` / ``ui.auto_scroll_run_log``, or ``None``.

        fast-synchronous -- a settings-store read.
        """
        ...

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist ``ui.run_log_verbosity`` / ``ui.auto_scroll_run_log``.

        fast-synchronous -- a settings-store write.
        """
        ...

    def manual_provider_probe(self) -> None:
        """Trigger a manual provider probe (the stability "retry probe" action).

        fast-synchronous -- enqueues the probe to a ``TaskRunner`` worker and
        returns; the result arrives later via ``_model_stability_changed``.
        Never a direct breaker call (D-R-06).
        """
        ...

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        """Return every run header.

        fast-synchronous -- a bounded store read. Structurally satisfies
        ``ui.common_dialogs.protocols.RenameRunGateway.list_runs`` for the
        header rename-pencil's V-5 name-uniqueness check (gap resolution
        above).
        """
        ...

    def is_run_active(self) -> bool:
        """Whether a run is currently executing (non-terminal).

        fast-synchronous. Read by the SPEC-098 bounded reconciliation timer on
        expiry, alongside ``run_header(run_id).status``, to recover from a
        lost terminal event (gap resolution above).
        """
        ...
