"""``MainWindowGateway``/``NewBenchmarkGateway``/``ProgressGateway``/``ResultGateway``/
``ResumeGateway``/``TaskEditorGateway`` -- **deliberate duplicates** of
``ui/main_window/protocols.py``, ``ui/new_benchmark/protocols.py``,
``ui/progress/protocols.py``, ``ui/results/protocols.py``,
``ui/resume_benchmark/protocols.py``, and ``ui/task_editor/protocols.py`` respectively.
Also declares ``ManualProviderProbeCommand`` and ``RunLogWriteStatus``, the two
adapter-local collaborator Protocols the concrete ``ProgressGateway`` implementation
depends on (see ``_internal/progress/gateway.py``'s docstring for why each is
adapter-local/single-consumer rather than a named backend service), ``ActiveRunTaskPaths``,
the adapter-local collaborator Protocol the concrete ``TaskEditorGateway`` implementation
depends on for the in-use-task-file marker (see below for why it is adapter-local), and
``JudgeAnalysisGenerationOutcome`` / ``JudgeAnalysisGenerationResult``, the locally-declared
mirrors of ``backend.run_analysis.RunAnalysisOutcome`` / ``RunAnalysisResult`` that
``ResultGateway.regenerate_run_analysis`` returns through its ``on_complete`` callback
(``ui/results/`` may not import ``backend.run_analysis`` directly, per STORY-061's
Definition of done -- see ``ui/results/protocols.py``'s own docstring for the full
rationale, mirrored here for the same reason as every other duplicate in this module).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.1 (``MainWindowGateway``), §7b.2 (``NewBenchmarkGateway``), §7b.3 (``ResumeGateway``),
§7b.4 (``ProgressGateway``), §7b.5 (``ResultGateway``), §7b.7 (``TaskEditorGateway``).

``ResultGateway.chart_data``'s return type is ``ChartData | HeatmapData`` here, matching
``ui/results/protocols.py``'s own copy (corrected by the STORY-108 spec-conformance fix
pass): ``ChartAggregator.compute`` (this gateway's actual collaborator) returns
``ChartData | HeatmapData`` for the ``HEATMAP_TASK_BY_MODEL`` chart kind, and the Charts
tab controller's own cache is already typed ``dict[ChartKind, ChartData | HeatmapData]``
(see ``ui/results/_internal/charts_tab/controller.py``). Both copies now declare the same
wider type, so ``_ResultGateway`` structurally satisfies both Protocols under
``mypy --strict``.

Each owning UI module's ``protocols.py`` stays the source of truth for its gateway's
shape: the widget owns it, but ``adapters/*`` may not import ``ui/*``
(``import-linter``), so this module's ``api.py`` cannot annotate a `make_*_gateway`
factory's return type with the UI module's copy. These copies exist only so ``api.py``
has something to annotate. Each concrete gateway class satisfies both its own copy here
and the UI module's copy structurally, with no import in either direction. Any change to
one side of a pair must be mirrored in the other.

This duplication resolves a contradiction inside ADR-0014 rather than applying it: the
ADR's decision item 2 requires each factory to return "the corresponding **UI-declared**
gateway Protocol type", while item 3 requires that ``adapters/ui_gateways/`` "declares no
gateway Protocol of its own" and never imports the UI module. Those two cannot both hold
-- annotating with the UI-declared type *is* importing the UI module. Item 3's layering
rule is the one with teeth (it is now enforced by the "Adapters never import the UI
layer" ``import-linter`` contract), so item 2 is satisfied structurally instead of
nominally, at the cost of item 3's "no Protocol of its own". A corrective ADR should
record that; ADR-0014 itself is accepted and so may no longer be edited in place
(``14_Process_and_Traceability/04_ADR_FORMAT.md`` §8).
"""

from collections.abc import Callable
from enum import StrEnum
from typing import Protocol

import msgspec

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ChartData,
    ChartKind,
    HeatmapData,
    InferenceTestResult,
    ModelCapabilityRecord,
    ModelName,
    ProviderConfig,
    ProviderId,
    ResultId,
    ResultPatch,
    RunId,
    RunStartRequest,
    RunStatusPatch,
    SettingKey,
)
from ollama_llm_bench.backend.run_drift import DriftWarning

__all__: list[str] = [
    "ActiveRunTaskPaths",
    "JudgeAnalysisGenerationOutcome",
    "JudgeAnalysisGenerationResult",
    "MainWindowGateway",
    "ManualProviderProbeCommand",
    "NewBenchmarkGateway",
    "PreviewGroup",
    "ProgressGateway",
    "ProviderImportPreview",
    "ProviderImportPreviewRow",
    "ProviderImportResult",
    "ResultGateway",
    "ResumeGateway",
    "RunLogWriteStatus",
    "SettingsGateway",
    "SettingsImportPreview",
    "SettingsImportPreviewRow",
    "SettingsImportResult",
    "Severity",
    "TaskEditorGateway",
    "ValidationFinding",
]


class ActiveRunTaskPaths(Protocol):
    """Adapter-local collaborator resolving the currently executing run's task-file
    paths, for the Task Editor's in-use marker (STORY-111-AC-1).

    No backend Protocol tracks this today -- ``RunRegistryStore`` only exposes
    ``active_run_id()`` (which run, not its task files), and
    ``RunStartRequest.task_paths`` is explicitly never persisted
    (``10_Domain_and_Data/02_DTOS_AND_ENUMS.md`` §7.3: "The request is consumed
    at run creation; it is never persisted."). Whatever future
    component actually persists/tracks a run's originating task-file paths (out of
    this story's scope) is the natural owner of this state; this Protocol is the
    gateway's read-only query surface onto it, scoped to exactly the one lookup
    ``TaskEditorGateway.active_run_task_paths()`` needs once it already knows a run
    is active.
    """

    def task_paths_for(self, run_id: RunId) -> tuple[str, ...]:
        """Return the absolute task-file paths backing ``run_id``.

        fast-synchronous. ``run_id`` is always a currently-active run id (the
        caller short-circuits on ``None`` before calling this).
        """
        ...


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


class MainWindowGateway(Protocol):
    """Adapter gateway for the Main Window shell (D-R-06).

    Mirror of ``ui.main_window.protocols.MainWindowGateway`` -- see this module's
    docstring for why the declaration is duplicated.
    """

    def get_window_geometry(self) -> str | None:
        """Read the persisted ``ui.window_geometry`` blob, or ``None`` if unset."""
        ...

    def set_window_geometry(self, value: str) -> None:
        """Persist the ``ui.window_geometry`` blob (debounced by the caller)."""
        ...

    def get_splitter_sizes(self) -> str | None:
        """Read the persisted ``ui.splitter_sizes``, or ``None`` if unset."""
        ...

    def set_splitter_sizes(self, value: str) -> None:
        """Persist ``ui.splitter_sizes``."""
        ...

    def get_active_workspace(self) -> str | None:
        """Read the persisted ``ui.active_workspace`` (``"benchmark"``/``"task_editor"``)."""
        ...

    def set_active_workspace(self, value: str) -> None:
        """Persist ``ui.active_workspace``."""
        ...

    def get_theme(self) -> str:
        """Read the resolved ``ui.theme`` setting."""
        ...

    def set_theme(self, value: str) -> None:
        """Persist ``ui.theme``."""
        ...

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        """Return the current readiness snapshot for the status-bar dot."""
        ...

    def reprobe(self) -> None:
        """Trigger a readiness re-probe (on a worker thread) on a dot click.

        The parenthetical is §7b.1's wording and means only "not on the graphical
        thread". The batch itself is orchestrated on the pipeline-dispatcher thread,
        never on a ``TaskRunner`` worker: ``08-E`` §12 and
        ``16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`` §4a both name the
        readiness ``probe_all`` batch as dispatcher-thread work, because it fans leaf
        probes out to the pool and blocks on them -- and a pool thread waiting on pool
        threads is the forbidden submit-and-wait pattern (STORY-105-AC-2).
        """
        ...

    def is_run_active(self) -> bool:
        """Whether a run is currently active (non-terminal) -- the quit decision."""
        ...

    def shutdown(self, timeout_ms: int) -> None:
        """Stop the active run gracefully on application quit (bounded wait)."""
        ...


class NewBenchmarkGateway(Protocol):
    """Adapter gateway for the New Benchmark widget (D-R-06).

    Mirror of ``ui.new_benchmark.protocols.NewBenchmarkGateway`` -- see this module's
    docstring for why the declaration is duplicated.
    """

    def get_setting(self, key: SettingKey) -> str | None:
        """Read a user-saved setting (Advanced-Options defaults,
        ``benchmark.last_mode``, ``embedding.hide_from_test_models``), or ``None``.

        fast-synchronous.
        """
        ...

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist a user-saved setting (e.g. ``benchmark.last_mode``).

        fast-synchronous.
        """
        ...

    def provider_list(self) -> tuple[ProviderConfig, ...]:
        """Return the enabled providers, in display order, for the model picker.

        fast-synchronous.
        """
        ...

    def readiness_snapshot(self) -> AppReadinessSnapshot:
        """Return the current readiness snapshot for the pre-run readiness gate.

        fast-synchronous.
        """
        ...

    def start_run(self, request: RunStartRequest) -> RunId:
        """Start a benchmark run from the assembled request; returns the run id.

        fast-synchronous (enqueues to the dispatcher thread and returns).
        """
        ...

    def notify_error(self, message: str) -> None:
        """Surface a non-blocking, user-facing error toast (STORY-055-AC-7).

        fast-synchronous. Used when the Run Summary dialog factory refuses to open
        (the preflight re-check failed) -- the widget's own fields stay untouched.
        ``message`` is passed through unchanged -- UI/display surfaces do not apply
        redaction (``08-E`` §22, STORY-106-AC-3).
        """
        ...


class ProgressGateway(Protocol):
    """Adapter gateway for the Progress widget (D-R-06).

    Mirror of ``ui.progress.protocols.ProgressGateway`` -- see this module's
    docstring for why the declaration is duplicated. See that module's own
    docstring for the full rationale behind the three methods
    (``list_runs``, ``is_run_active``, ``run_log_write_failed``) that extend
    beyond ``08-E`` §7b.4's eleven verbatim methods.
    """

    def pause_run(self) -> None:
        """Request a cooperative pause of the active run."""
        ...

    def resume_run(self) -> None:
        """Resume execution after a pause."""
        ...

    def stop_run(self, reason: str | None = None) -> None:
        """Request a cooperative stop of the active run."""
        ...

    def run_metadata(self, run_id: RunId) -> BenchmarkRun:
        """Read the active run's metadata from the run registry."""
        ...

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        """Set or clear the active run's user-facing name (the inline pencil)."""
        ...

    def run_header(self, run_id: RunId) -> BenchmarkRun:
        """Read a run header -- elapsed time and the terminal run summary."""
        ...

    def task_counters(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Read per-task result rows for the run-progress counters / current task."""
        ...

    def load_past_log(self, run_id: RunId) -> str:
        """Load the saved run-log of a past run for replay."""
        ...

    def get_setting(self, key: SettingKey) -> str | None:
        """Read ``ui.run_log_verbosity`` / ``ui.auto_scroll_run_log``, or ``None``."""
        ...

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist ``ui.run_log_verbosity`` / ``ui.auto_scroll_run_log``."""
        ...

    def manual_provider_probe(self) -> None:
        """Trigger a manual provider probe (the stability "retry probe" action)."""
        ...

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        """Return every run header.

        Structurally satisfies
        ``ui.common_dialogs.protocols.RenameRunGateway.list_runs`` for the
        header rename-pencil's name-uniqueness check.
        """
        ...

    def is_run_active(self) -> bool:
        """Whether a run is currently executing (non-terminal)."""
        ...

    def run_log_write_failed(self) -> bool:
        """Whether the run-log file writer's most recent write attempt failed."""
        ...


class JudgeAnalysisGenerationOutcome(StrEnum):
    """Locally-declared mirror of ``backend.run_analysis.RunAnalysisOutcome``.

    See this module's docstring for why the mirror exists.
    """

    GENERATED = "generated"
    SKIPPED = "skipped"
    FAILED = "failed"


class JudgeAnalysisGenerationResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Locally-declared mirror of ``backend.run_analysis.RunAnalysisResult``.

    ``provider_name`` is the analysis provider's display **name** snapshot,
    populated by the concrete gateway (which alone holds ``ProviderRegistry``
    access) when ``outcome`` is ``GENERATED`` -- never the internal
    ``provider_id``. See this module's docstring for why the mirror exists.
    """

    outcome: JudgeAnalysisGenerationOutcome
    run_analysis_markdown: str | None = None
    error_message: str | None = None
    is_regeneration: bool = False
    provider_name: str | None = None


class ResultGateway(Protocol):
    """Adapter gateway for the Result widget (D-R-06).

    Mirror of ``ui.results.protocols.ResultGateway`` -- see this module's
    docstring for why the declaration is duplicated, including the deliberate
    ``chart_data`` return-type widening.
    """

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        """Return the run headers for the run-selector dropdown."""
        ...

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        """Read one run header (for the active-run analysis and metadata)."""
        ...

    def persist_run_analysis(self, run_id: RunId, patch: RunStatusPatch) -> None:
        """Persist the consolidated ``run_analysis`` via a run-header patch."""
        ...

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Read a run's results for the Summary / Details / Charts / Analysis caches."""
        ...

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        """Read per-task metadata (question, golden answer, required terms)."""
        ...

    def get_setting(self, key: SettingKey) -> str | None:
        """Read ``ui.last_result_tab`` / ``ui.export_save_directly`` /
        ``ui.score_display_format``, or ``None``."""
        ...

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist ``ui.last_result_tab`` / ``ui.export_save_directly``."""
        ...

    def regenerate_run_analysis(
        self,
        run_id: RunId,
        provider_id: ProviderId,
        model_name: ModelName,
        *,
        on_complete: Callable[[JudgeAnalysisGenerationResult], None],
    ) -> bool:
        """Attempt to acquire ``JUDGE_ANALYSIS`` and dispatch run-analysis generation.

        fast-synchronous: performs a fast pre-check and, when the gate is
        free, submits ``RunAnalysisService.generate(run_id, provider_id,
        model_name)`` to a worker thread, returning ``True`` immediately.
        ``on_complete`` is invoked on the GUI thread with the terminal
        ``JudgeAnalysisGenerationResult`` once the call settles. Returns
        ``False``, without dispatching and without ever calling
        ``on_complete``, when the pre-check finds the gate already held by
        another activity.
        """
        ...

    def chart_data(self, run_id: RunId, chart_kind: ChartKind) -> ChartData | HeatmapData:
        """Compute one chart's prepared ``ChartData`` / ``HeatmapData``."""
        ...

    def serialize_table(self, run_id: RunId, table: str, fmt: str) -> str:
        """Produce the Summary / Details CSV or Markdown payload."""
        ...


class ResumeGateway(Protocol):
    """Adapter gateway for the Resume Benchmark widget (D-R-06).

    Mirror of ``ui.resume_benchmark.protocols.ResumeGateway`` -- see this module's
    docstring for why the declaration is duplicated. Also structurally satisfied
    by whatever concrete class implements ``ui.common_dialogs.protocols``'
    ``RenameRunGateway``/``ResumeSummaryGateway``/``RetrySelectionGateway``.
    """

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

    def detect_drift(self, run_id: RunId) -> tuple[DriftWarning, ...]:
        """Run the Run Drift Detector fresh against the current environment.

        Blocking -- refreshes readiness (fans per-provider handshakes out onto
        the worker pool and joins them, then runs the single embedding probe)
        before comparing the run's frozen snapshot; must not be invoked
        directly on the GUI thread. Never raises; every environment-availability
        problem is reported as a returned ``DriftWarning``, never an exception
        (11_RUN_DRIFT_DETECTOR.md).
        """
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

    def serialize_table(self, run_id: RunId, table: str, fmt: str) -> str:
        """Produce the Summary / Details CSV or Markdown payload.

        ``table`` is ``"summary"``/``"details"``, ``fmt`` is ``"csv"``/``"markdown"``
        -- the same token vocabulary as ``ResultGateway.serialize_table`` so both
        gateways can share one ``TableSerializer`` collaborator.
        """
        ...


class Severity(StrEnum):
    """Locally-declared mirror of ``ui.settings_dialog.models.Severity`` /
    ``backend.import_export.models.ImportFindingSeverity`` -- see this
    module's docstring for why the declaration is duplicated."""

    HARD_ERROR = "hard_error"
    SOFT_WARNING = "soft_warning"
    SOFT_INFO = "soft_info"


class ValidationFinding(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Locally-declared mirror of ``ui.settings_dialog.models.ValidationFinding``.

    ``target`` mirrors ``backend.import_export.models.ImportFinding.item_key``,
    coerced to ``""`` for a file-level finding (``item_key is None``) since
    the UI-declared shape this mirrors has no optional ``target``.
    """

    severity: Severity
    target: str
    message: str


class PreviewGroup(StrEnum):
    """Locally-declared mirror of ``ui.settings_dialog.models.PreviewGroup`` /
    ``backend.import_export.models.ImportPreviewGroup``."""

    ADDED = "added"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    SKIPPED = "skipped"


class SettingsImportPreviewRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Locally-declared mirror of
    ``ui.settings_dialog.models.SettingsImportPreviewRow``."""

    setting_key: SettingKey
    current_value: str | None
    imported_value: str | None
    group: PreviewGroup


class SettingsImportPreview(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Locally-declared mirror of ``ui.settings_dialog.models.SettingsImportPreview``.

    ``backend_preview`` is a deliberate extension beyond the UI-declared
    shape: it carries the original ``backend.import_export.models
    .SettingsImportPreview`` this preview was translated from, so
    ``apply_settings_import`` can round-trip the *same* object the
    Settings dialog's controller passes straight back (unread by any other
    field) without ``adapters/ui_gateways/`` needing to reconstruct a
    backend preview from display-only fields.
    """

    rows: tuple[SettingsImportPreviewRow, ...]
    findings: tuple[ValidationFinding, ...]
    resolved_values: dict[SettingKey, str]
    backend_preview: object


class SettingsImportResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Locally-declared mirror of ``ui.settings_dialog.models.SettingsImportResult``."""

    applied_count: int
    skipped_count: int


class ProviderImportPreviewRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Locally-declared mirror of
    ``ui.settings_dialog.models.ProviderImportPreviewRow``."""

    name: str
    group: PreviewGroup


class ProviderImportPreview(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Locally-declared mirror of ``ui.settings_dialog.models.ProviderImportPreview``.

    ``backend_preview`` -- see ``SettingsImportPreview``'s docstring; same
    round-trip rationale, here carrying the original
    ``backend.import_export.models.ProviderImportPreview`` (whose entries
    carry the ``ProviderConfigDraft`` values ``apply_provider_import``
    actually needs -- display-only ``rows`` never carry a draft).
    """

    rows: tuple[ProviderImportPreviewRow, ...]
    embedding_provider_name: str | None
    embedding_model_name: str | None
    findings: tuple[ValidationFinding, ...]
    backend_preview: object


class ProviderImportResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Locally-declared mirror of ``ui.settings_dialog.models.ProviderImportResult``."""

    applied_count: int
    skipped_count: int


class SettingsGateway(Protocol):
    """Adapter gateway for the Settings Dialog (D-R-06).

    Mirror of ``ui.settings_dialog.protocols.SettingsGateway`` -- see this
    module's docstring for why the declaration is duplicated. Four methods
    diverge from ``08-E`` §7b.6's verbatim text per ADR-0015: ``test_provider``
    and ``discover_models`` return ``None`` and gain a keyword-only
    ``on_complete`` callback; ``probe_all`` and ``probe_embedding`` return
    ``None`` with no callback (their result reaches the caller via the
    existing ``_app_readiness_changed`` event instead).
    """

    def list_providers(self) -> tuple[ProviderConfig, ...]: ...
    def get_provider_by_name(self, name: str) -> ProviderConfig | None: ...
    def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None: ...
    def get_setting(self, key: SettingKey) -> str | None: ...
    def list_settings(self) -> dict[SettingKey, str]: ...
    def upsert_settings(self, values: dict[SettingKey, str]) -> None: ...
    def get_resolved_str(self, key: SettingKey) -> str: ...

    def list_model_capabilities(
        self, provider_id: ProviderId, model_name: ModelName
    ) -> tuple[ModelCapabilityRecord, ...]: ...

    def upsert_model_capability(self, record: ModelCapabilityRecord) -> None: ...

    def test_provider(
        self,
        provider_id: ProviderId,
        model_name: ModelName,
        *,
        on_complete: Callable[[InferenceTestResult], None],
    ) -> None:
        """Run the per-row/reachability/inference test probe (ADR-0015).

        fast-synchronous: returns before the probe completes. Submitted to a
        ``TaskRunner`` worker thread; ``on_complete`` is invoked on the GUI
        thread with the result once the call settles. Acquires the
        ``PROVIDER_TEST`` single-inference gate for the call's full duration
        and releases it in ``finally``; yields
        ``InferenceTestResult(outcome=GATE_BUSY, ...)`` via ``on_complete``
        without issuing a call when the gate is held elsewhere. An empty
        ``model_name`` runs the reachability-only probe (``probe_health``);
        a non-empty ``model_name`` runs the end-to-end inference probe
        (``test_inference``) -- the existing single-entry-point convention
        this gateway must preserve unchanged (see
        ``ui/settings_dialog/_internal/sub_dialogs/provider_edit_view.py``'s
        module docstring).
        """
        ...

    def discover_models(
        self,
        provider_id: ProviderId,
        *,
        on_complete: Callable[[tuple[ModelName, ...]], None],
    ) -> None:
        """Discover a provider's models for the embedding-section picker (ADR-0015).

        fast-synchronous: returns before discovery completes. Submitted to a
        ``TaskRunner`` worker thread; ``on_complete`` is invoked on the GUI
        thread with the result once the call settles.
        """
        ...

    def probe_all(self) -> None:
        """Run the auto-check on open (ADR-0015).

        fast-synchronous: returns before the batch completes. Submitted to
        the pipeline-dispatcher thread (never a ``TaskRunner`` worker -- this
        is a fan-out-and-join batch, and a pool worker must never
        submit-and-wait on the pool, ``04_CONCURRENCY_STANDARD.md`` §4a).
        No callback: ``ReadinessService`` emits ``_app_readiness_changed``
        itself once the batch completes; the Settings dialog already
        subscribes to it.
        """
        ...

    def probe_embedding(self) -> None:
        """Run the billable Test Embedding capability probe (ADR-0015).

        fast-synchronous: returns before the probe completes. Submitted to a
        ``TaskRunner`` worker thread. No callback parameter -- unlike
        ``probe_all``, this gateway publishes ``_app_readiness_changed``
        itself once the probe settles (see this story's plan for why:
        ``ReadinessService`` has no method for this billable check, and this
        method must not call ``ReadinessService.probe_all()`` from a worker
        thread). The Settings dialog's existing subscription repaints the
        embedding diagnostic with no new UI wiring.
        """
        ...

    def readiness_snapshot(self) -> AppReadinessSnapshot: ...
    def build_settings_import_preview(self, file_path: str) -> SettingsImportPreview: ...
    def apply_settings_import(self, preview: SettingsImportPreview) -> SettingsImportResult: ...
    def build_provider_import_preview(self, file_path: str) -> ProviderImportPreview: ...
    def apply_provider_import(self, preview: ProviderImportPreview) -> ProviderImportResult: ...
    def export_settings(self) -> bytes: ...
    def export_providers(self) -> bytes: ...

    def save_all(
        self, *, providers: tuple[ProviderConfig, ...], settings_values: dict[SettingKey, str]
    ) -> None: ...

    def reset_to_defaults(self, *, bundled_providers: tuple[ProviderConfig, ...]) -> None: ...


class TaskEditorGateway(Protocol):
    """Adapter gateway for the Task Editor workspace (D-R-06).

    Mirror of ``ui.task_editor.protocols.TaskEditorGateway`` -- see this module's
    docstring for why the declaration is duplicated.
    """

    def get_setting(self, key: SettingKey) -> str | None:
        """Read a workspace settings key, or ``None`` if unset.

        fast-synchronous. Keys: ``task_editor.auto_format_on_save``,
        ``task_editor.warn_on_empty_grading_criteria``,
        ``task_editor.validation_debounce_ms``, ``ui.task_editor_last_folder``.
        """
        ...

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist a workspace settings key (e.g. ``ui.task_editor_last_folder``).

        fast-synchronous.
        """
        ...

    def active_workspace(self) -> str:
        """Read the current active workspace (``"benchmark"``/``"task_editor"``).

        fast-synchronous.
        """
        ...

    def active_run_task_paths(self) -> tuple[str, ...]:
        """Read the active run's task file paths for the in-use marker.

        fast-synchronous. Returns the absolute paths of every task file backing
        the currently executing run, or ``()`` when no run is active.
        """
        ...
