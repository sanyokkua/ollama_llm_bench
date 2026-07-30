"""The concrete ``ProgressGateway`` implementation (STORY-107).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.4 (``ProgressGateway``), §7b (UI adapter gateways, D-R-06), §4 (the threading
contract); ``ui/progress/protocols.py`` (the widget-side Protocol this class
satisfies, including its three locally-added extension methods).

Three collaborators wired here have no matching backend Protocol today; see the
planning note in this story's plan file for why:

- ``load_past_log`` reads the run's saved log file directly via ``pathlib`` (no
  ``RunLogReader`` Protocol exists anywhere in the codebase).
- ``manual_provider_probe`` and ``run_log_write_failed`` each delegate to a tiny,
  adapter-local collaborator Protocol declared below (``ManualProviderProbeCommand``,
  ``RunLogWriteStatus``) rather than a named backend service, because no backend
  component resolves "which provider" or tracks "the last run-log write outcome"
  yet -- that production wiring is explicitly out of this story's scope.
"""

from typing import Protocol

from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi
from ollama_llm_bench.backend.concurrency import (
    CancellationToken,
    TaskRunner,
    make_cancellation_token,
)
from ollama_llm_bench.backend.domain import BenchmarkResult, BenchmarkRun, RunId, SettingKey
from ollama_llm_bench.backend.infra import run_log_dir
from ollama_llm_bench.backend.infra.protocols import Clock, PlatformDetector
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.persistence.results import ResultsStore
from ollama_llm_bench.backend.persistence.runs import RunsStore
from ollama_llm_bench.backend.settings import SettingsService

__all__: list[str] = [
    "ManualProviderProbeCommand",
    "ProgressGatewayCollaborators",
    "RunLogWriteStatus",
    "_ProgressGateway",
]


class ManualProviderProbeCommand(Protocol):
    """Adapter-local collaborator backing the stability panel's manual retry-probe action.

    Scoped to exactly what ``ProgressGateway.manual_provider_probe()`` needs: one
    no-argument probe operation, submitted to a ``TaskRunner`` worker by the
    gateway. Which provider is probed, and how the outcome reaches the
    ``_model_stability_changed`` bus event, is this collaborator's own concern --
    deferred to whichever future story wires a real implementation (this story
    scopes only the gateway's dispatch onto a worker thread, not that wiring).
    """

    def probe(self) -> None:
        """Perform one provider health probe. Blocking; runs on a ``TaskRunner`` worker."""
        ...


class RunLogWriteStatus(Protocol):
    """Adapter-local collaborator answering "did the run-log file writer's most
    recent write attempt fail" (EC-LOG-1).

    No backend Protocol tracks this today -- ``RunLogWriter.write_event()``
    returns a ``WriteOutcome`` per call but nothing persists the last one.
    Whatever future component drives ``RunLogWriter.write_event()`` from bus
    events (out of this story's scope) is the natural owner of this state; this
    Protocol is the gateway's read-only query surface onto it.
    """

    def write_failed(self) -> bool:
        """Whether the most recent write attempt failed. fast-synchronous."""
        ...


class ProgressGatewayCollaborators:
    """Groups the concrete gateway's constructor dependencies (<=4-parameter rule).

    A plain, private-implementation-detail bundle -- not a cross-boundary DTO, so
    it is an ordinary class rather than a ``msgspec.Struct``; it never leaves this
    ``_internal`` package.
    """

    def __init__(  # noqa: PLR0913  # this class exists solely to bundle these ten
        # distinct required collaborators (<=4-parameter rule via a dependency bundle)
        self,
        *,
        flow: BenchmarkFlowApi,
        runs_store: RunsStore,
        results_store: ResultsStore,
        app_settings: AppSettingsStore,
        settings: SettingsService,
        platform_detector: PlatformDetector,
        task_runner: TaskRunner[object],
        clock: Clock,
        probe_command: ManualProviderProbeCommand,
        write_status: RunLogWriteStatus,
    ) -> None:
        self.flow = flow
        self.runs_store = runs_store
        self.results_store = results_store
        self.app_settings = app_settings
        self.settings = settings
        self.platform_detector = platform_detector
        self.task_runner = task_runner
        self.clock = clock
        self.probe_command = probe_command
        self.write_status = write_status


class _ProgressGateway:
    """Adapter gateway for the Progress widget, satisfying
    ``ui.progress.protocols.ProgressGateway`` structurally (D-R-06).

    Also satisfies ``ui.common_dialogs.protocols.RenameRunGateway`` structurally
    with no extra adapter class (``list_runs``/``rename_run`` match verbatim) --
    proven by STORY-104-AC-2, not retested here. Construction is side-effect
    free: it performs no read, no probe, and no network call (STORY-107-AC-4).
    """

    def __init__(self, *, collaborators: ProgressGatewayCollaborators) -> None:
        self._c = collaborators

    def pause_run(self) -> None:
        """Request a cooperative pause of the active run."""
        self._c.flow.pause()

    def resume_run(self) -> None:
        """Resume execution after a pause (not a crash-recovery resume)."""
        self._c.flow.resume_paused()

    def stop_run(self, reason: str | None = None) -> None:  # noqa: ARG002
        # `reason` is part of the verbatim 08-E §7b.4 signature but is never
        # forwarded: BenchmarkFlowApi.stop() takes no argument -- CancelReason
        # is a closed enum, never free text (DD-42).
        """Request a cooperative stop of the active run."""
        self._c.flow.stop()

    def run_metadata(self, run_id: RunId) -> BenchmarkRun:
        """Read the active run's metadata from the runs store."""
        return self._c.runs_store.get_run(run_id)

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        """Set or clear the active run's user-facing name (the inline pencil)."""
        self._c.runs_store.rename_run(run_id, name)

    def run_header(self, run_id: RunId) -> BenchmarkRun:
        """Read a run header -- elapsed time and the terminal run summary."""
        return self._c.runs_store.get_run(run_id)

    def task_counters(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Read per-task result rows for the run-progress counters / current task."""
        return self._c.results_store.list_results(run_id)

    def load_past_log(self, run_id: RunId) -> str:
        """Load the saved run-log of a past run for replay.

        Returns an empty string when no matching file exists (a pruned or
        missing log), never raises.
        """
        log_dir = run_log_dir(self._c.platform_detector)
        matches = sorted(log_dir.glob(f"run_{run_id}_*.log"))
        if not matches:
            return ""
        return matches[-1].read_text(encoding="utf-8")

    def get_setting(self, key: SettingKey) -> str | None:
        """Read ``ui.run_log_verbosity`` / ``ui.auto_scroll_run_log``, or ``None``."""
        return self._c.app_settings.get_setting(key)

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist ``ui.run_log_verbosity`` / ``ui.auto_scroll_run_log``."""
        self._c.settings.set(key, value)

    def manual_provider_probe(self) -> None:
        """Submit a manual provider probe to a worker thread and return immediately."""
        token: CancellationToken = make_cancellation_token(clock=self._c.clock)
        self._c.task_runner.submit(self._c.probe_command.probe, token=token)

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        """Return every run header."""
        return self._c.runs_store.list_runs()

    def is_run_active(self) -> bool:
        """Whether a run is currently executing (non-terminal)."""
        return self._c.flow.is_running()

    def run_log_write_failed(self) -> bool:
        """Whether the run-log file writer's most recent write attempt failed."""
        return self._c.write_status.write_failed()
