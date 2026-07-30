"""The concrete ``ResultGateway`` implementation (STORY-108).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.5 (``ResultGateway``), §7b (UI adapter gateways, D-R-06), §4 (the threading
contract); ``docs/v3_specification/11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md``
§2.1 (``RunAnalysisService.generate``'s public surface) and §9 (threading); the
``ui/results/protocols.py`` Protocol this class satisfies structurally.

Two design points worth calling out:

- ``chart_data`` passes ``ChartFilters()`` (every field at its default) to
  ``ChartAggregator.compute`` because ``ResultGateway.chart_data(run_id, chart_kind)``
  (08-E §7b.5, frozen by STORY-061) carries no filter parameter -- the Charts tab
  controller cannot forward its filter-chip/per-chart-option selection through this
  call today (a documented gap; see
  ``ui/results/_internal/charts_tab/controller.py``'s own module docstring). This
  story does not change that signature or close that gap.
- ``regenerate_run_analysis`` never passes ``inside_pipeline=True`` to
  ``RunAnalysisService.generate`` -- that keyword is a concrete-class-only extension
  of the Protocol (``RunAnalysisServiceImpl``'s own docstring), reserved for the
  benchmark pipeline's own finalization step. The user-facing on-demand path this
  gateway serves always takes the Protocol's bare three-argument signature, so the
  service performs its own atomic ``try_acquire``/``release`` around the call
  (``22_RUN_ANALYSIS_SERVICE.md`` §6.1a). This gateway's own ``is_busy()`` check is
  therefore only a fast pre-check, not a held lease -- the tiny window between that
  peek and the service's own acquire is the documented "safety net" race in §6.1a
  step 5, which degrades to a ``FAILED`` result delivered through ``on_complete``,
  never a crash.
"""

from collections.abc import Callable, Iterable
from concurrent.futures import Future
import functools
from importlib.metadata import PackageNotFoundError, version as _package_version
from typing import Final, cast

from PySide6.QtCore import QObject, Qt, Signal, Slot

from ollama_llm_bench.adapters.ui_gateways.protocols import (
    JudgeAnalysisGenerationOutcome,
    JudgeAnalysisGenerationResult,
)
from ollama_llm_bench.backend.charts import ChartAggregator
from ollama_llm_bench.backend.concurrency import (
    CancellationToken,
    TaskRunner,
    make_cancellation_token,
)
from ollama_llm_bench.backend.csv_export import (
    DetailsSerializationRequest,
    RunExportContext,
    SummaryRow,
    SummarySerializationRequest,
    TableSerializer,
)
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ChartData,
    ChartFilters,
    ChartKind,
    HeatmapData,
    ModelName,
    PositiveInt,
    ProviderId,
    ResultStatus,
    RunId,
    RunStatusPatch,
    SettingKey,
    Verdict,
)
from ollama_llm_bench.backend.errors import ContractViolationError
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.persistence.results import ResultsStore
from ollama_llm_bench.backend.persistence.runs import RunsStore
from ollama_llm_bench.backend.persistence.tasks import TasksStore
from ollama_llm_bench.backend.provider_registry import ProviderRegistry
from ollama_llm_bench.backend.run_analysis import (
    RunAnalysisOutcome,
    RunAnalysisResult,
    RunAnalysisService,
)
from ollama_llm_bench.backend.settings import SettingsService
from ollama_llm_bench.backend.stores.inference_activity import InferenceActivityStore

__all__: list[str] = [
    "ResultGatewayCollaborators",
    "_ResultGateway",
]

_ERROR_STATUSES: Final[frozenset[ResultStatus]] = frozenset(
    {
        ResultStatus.FAILED_INFERENCE,
        ResultStatus.FAILED_PROVIDER,
        ResultStatus.FAILED_TIMEOUT,
        ResultStatus.FAILED_JUDGE_TIMEOUT,
        ResultStatus.ERRORED,
    }
)
_MIN_SAMPLE_SIZE_KEY: Final[SettingKey] = "eval.min_sample_size"
_MS_PER_SECOND: Final[int] = 1000
# The two ``table`` tokens real callers actually send -- ``footer.py``'s
# ``_active_tab`` (lowercase, matching the tab-id vocabulary), never the
# capitalised ``ExportKind`` enum values, which name a different concept (the
# export *filename kind* token composed separately by ``footer.py``'s own
# ``_TABLE_KIND_BY_TAB`` mapping).
_TABLE_SUMMARY: Final[str] = "summary"
_TABLE_DETAILS: Final[str] = "details"


def _read_app_version() -> str:
    """Read this application's own distribution version (§5, `05_EXPORT_FORMATS.md`).

    No ``__version__``/app-version constant exists anywhere in the codebase today
    (confirmed by a repo-wide grep of ``backend/`` and the package root); the single
    version string lives in ``pyproject.toml``'s ``[project].version``, which
    ``importlib.metadata`` reads from the installed distribution's metadata --
    the standard-library mechanism for this, and one already exercised by this
    project's own editable install.
    """
    try:
        return _package_version("ollama-llm-bench")
    except PackageNotFoundError:
        return "0.0.0"


_APP_VERSION: Final[str] = _read_app_version()


def _effective_run_name(run: BenchmarkRun) -> str:
    """Best-effort display name for the export header.

    Mirrors the accepted simplified stand-in ``ui/results/_internal/controller.py``
    already uses for its own run-selector dropdown label -- the canonical
    generated-default-name template (SPEC-077) lives in ``ui/resume_benchmark``,
    a UI-layer module ``adapters/`` may not import.
    """
    return run.run_name or f"Run {run.run_id}"


def _mean_optional(values: Iterable[float | None]) -> float | None:
    """Arithmetic mean over the non-``None`` values, or ``None`` when none are present."""
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _mean_seconds(values_ms: Iterable[int | None]) -> float | None:
    """``_mean_optional`` over millisecond values, converted to seconds."""
    mean_ms = _mean_optional(values_ms)
    if mean_ms is None:
        return None
    return mean_ms / _MS_PER_SECOND


def _summarize_group(rows: list[BenchmarkResult]) -> SummaryRow:
    """Aggregate one ``(provider, model)`` group of raw result rows (§4, `05_EXPORT_FORMATS.md`)."""
    completed = [row for row in rows if row.status == ResultStatus.COMPLETED]
    passed_count = sum(1 for row in completed if row.verdict == Verdict.PASS)
    failed_count = sum(1 for row in completed if row.verdict == Verdict.FAIL)
    error_count = sum(1 for row in rows if row.status in _ERROR_STATUSES)
    first = rows[0]
    return SummaryRow(
        provider_id=first.provider_id,
        provider_name=first.provider_name,
        model_name=first.model_name,
        task_count=len(rows),
        completed_count=len(completed),
        passed_count=passed_count,
        failed_count=failed_count,
        pass_rate=(passed_count / len(completed)) if completed else None,
        avg_score=None,
        avg_cosine=_mean_optional(row.cosine_similarity for row in completed),
        avg_ttft_s=_mean_seconds(row.ttft_ms for row in completed),
        avg_total_time_s=_mean_seconds(row.total_time_ms for row in completed),
        avg_tps=_mean_optional(row.tokens_per_second for row in completed),
        error_count=error_count,
    )


def _build_summary_rows(results: tuple[BenchmarkResult, ...]) -> tuple[SummaryRow, ...]:
    """Aggregate raw result rows into one ``SummaryRow`` per ``(provider_id, model)`` pair.

    Groups preserve each pair's first-seen order. ``provider_name`` is always the
    group's own snapshot name (``BenchmarkResult.provider_name``, DD-33) -- this
    aggregation never consults ``ProviderRegistry``, so a later provider rename
    never rewrites a past export.
    """
    groups: dict[tuple[str, str], list[BenchmarkResult]] = {}
    for result in results:
        groups.setdefault((result.provider_id, result.model_name), []).append(result)
    return tuple(_summarize_group(rows) for rows in groups.values())


class _AnalysisCompletionRelay(QObject):
    """Private ``QObject`` marshalling one ``regenerate_run_analysis`` completion
    onto the GUI thread.

    Modelled on ``adapters/qt_event_bus/_internal/deliverer.py``'s
    ``_RelayCarrier`` -- see that module's docstring for the underlying reason a
    relay signal lives on its own tiny ``QObject`` rather than on the gateway
    itself.

    One instance is constructed per ``regenerate_run_analysis`` call. It is
    **not** kept alive by the emitting ``Future``'s done-callback closure alone
    -- that closure typically finishes (and can be garbage-collected) on the
    worker thread the instant ``emit()`` returns, which merely *posts* the
    queued event; nothing then guarantees the Python wrapper (and so the
    underlying C++ ``QObject``) survives on the GUI thread long enough for
    that posted event to actually be processed. ``_ResultGateway`` therefore
    holds its own strong reference to every in-flight relay
    (``_pending_relays``) from construction until ``on_delivered`` fires --
    always on the GUI thread, since ``_deliver`` runs there too.
    """

    _completed = Signal(object)

    def __init__(
        self,
        on_complete: Callable[[JudgeAnalysisGenerationResult], None],
        *,
        on_delivered: Callable[["_AnalysisCompletionRelay"], None],
    ) -> None:
        super().__init__()
        self._on_complete = on_complete
        self._on_delivered = on_delivered
        self._completed.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    def deliver(self, result: JudgeAnalysisGenerationResult) -> None:
        """Emit the relay signal; safe to call from any thread (typically a worker)."""
        self._completed.emit(result)

    @Slot(object)
    def _deliver(self, result: object) -> None:
        try:
            self._on_complete(cast("JudgeAnalysisGenerationResult", result))
        finally:
            self._on_delivered(self)


class ResultGatewayCollaborators:
    """Groups the concrete gateway's constructor dependencies (<=4-parameter rule).

    A plain, private-implementation-detail bundle -- not a cross-boundary DTO, so
    it is an ordinary class rather than a ``msgspec.Struct``; it never leaves this
    ``_internal`` package.
    """

    def __init__(  # noqa: PLR0913  # this class exists solely to bundle these twelve
        # distinct required collaborators (<=4-parameter rule via a dependency bundle)
        self,
        *,
        runs_store: RunsStore,
        results_store: ResultsStore,
        tasks_store: TasksStore,
        app_settings: AppSettingsStore,
        settings: SettingsService,
        run_analysis: RunAnalysisService,
        gate: InferenceActivityStore,
        provider_registry: ProviderRegistry,
        chart: ChartAggregator,
        serializer: TableSerializer,
        task_runner: TaskRunner[object],
        clock: Clock,
    ) -> None:
        self.runs_store = runs_store
        self.results_store = results_store
        self.tasks_store = tasks_store
        self.app_settings = app_settings
        self.settings = settings
        self.run_analysis = run_analysis
        self.gate = gate
        self.provider_registry = provider_registry
        self.chart = chart
        self.serializer = serializer
        self.task_runner = task_runner
        self.clock = clock


class _ResultGateway:
    """Adapter gateway for the Result widget, satisfying
    ``ui.results.protocols.ResultGateway`` structurally (D-R-06).

    Construction is side-effect free: it performs no read, no probe, and no
    network call (STORY-108-AC-5).
    """

    def __init__(self, *, collaborators: ResultGatewayCollaborators) -> None:
        self._c = collaborators
        self._pending_relays: set[_AnalysisCompletionRelay] = set()

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        """Return the run headers for the run-selector dropdown."""
        return self._c.runs_store.list_runs()

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        """Read one run header (for the active-run analysis and metadata)."""
        return self._c.runs_store.get_run(run_id)

    def persist_run_analysis(self, run_id: RunId, patch: RunStatusPatch) -> None:
        """Persist the consolidated ``run_analysis`` via a run-header patch."""
        self._c.runs_store.update_run_status(run_id, patch)

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Read a run's results for the Summary / Details / Charts / Analysis caches."""
        return self._c.results_store.list_results(run_id)

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        """Read per-task metadata (question, golden answer, required terms)."""
        return self._c.tasks_store.list_tasks(run_id)

    def get_setting(self, key: SettingKey) -> str | None:
        """Read ``ui.last_result_tab`` / ``ui.export_save_directly`` /
        ``ui.score_display_format``, or ``None``."""
        return self._c.app_settings.get_setting(key)

    def set_setting(self, key: SettingKey, value: str) -> None:
        """Persist ``ui.last_result_tab`` / ``ui.export_save_directly``."""
        self._c.settings.set(key, value)

    def chart_data(self, run_id: RunId, chart_kind: ChartKind) -> ChartData | HeatmapData:
        """Compute one chart's prepared ``ChartData`` / ``HeatmapData``.

        ``ChartFilters()`` (every field at its default) stands in for "no
        filter" -- see this module's docstring for the documented gap. The
        actual aggregation (``ChartAggregator.compute``) is dispatched to a
        ``TaskRunner`` worker and blocked on here -- ``13_CHART_AGGREGATORS.md``
        §10 requires aggregation to run on the background executor, never on
        the Qt UI thread; this method's own external signature stays
        synchronous (matching the Protocol) by blocking on the worker
        ``Future`` before returning, the same pattern
        ``regenerate_run_analysis`` uses for its own worker dispatch.
        """
        run = self._c.runs_store.get_run(run_id)
        results = self._c.results_store.list_results(run_id)
        tasks = self._c.tasks_store.list_tasks(run_id)
        min_sample_size = self._min_sample_size()
        token: CancellationToken = make_cancellation_token(clock=self._c.clock)
        future = self._c.task_runner.submit(
            functools.partial(
                self._c.chart.compute,
                chart_kind=chart_kind,
                run_mode=run.run_mode,
                results=results,
                tasks=tasks,
                filters=ChartFilters(),
                min_sample_size=min_sample_size,
            ),
            token=token,
        )
        return cast("ChartData | HeatmapData", future.result())

    def _min_sample_size(self) -> PositiveInt:
        """Resolve ``eval.min_sample_size`` through the settings cascade.

        Delegates to ``SettingsService.get_int`` rather than parsing
        ``AppSettingsStore.get_setting``'s raw string directly: a malformed
        stored value is user-editable settings data, not a programmer
        invariant, so it must be handled as data rather than crash. The
        settings-service cascade already applies the codebase's one
        established fallback rule for a malformed setting (SPEC-110): log a
        warning and fall back to the registry default (``"5"``) -- the same
        rule ``backend/readiness`` and ``backend/benchmark_pipeline`` already
        rely on for their own integer settings reads.
        """
        return self._c.settings.get_int(_MIN_SAMPLE_SIZE_KEY)

    def serialize_table(self, run_id: RunId, table: str, fmt: str) -> str:
        """Produce the Summary / Details CSV or Markdown payload.

        ``table`` is the tab-id token real callers send (``"summary"`` /
        ``"details"``, matching ``ui.results.protocols.ResultGateway`` and
        ``ui.resume_benchmark.protocols.ResumeGateway``'s shared
        ``serialize_table`` vocabulary) -- never the capitalised
        ``ExportKind`` enum values, which name the unrelated export-*filename*
        kind token. Runs inline on the calling thread by design: table
        serialization is explicitly carved out of the background-executor
        rule (`19_TABLE_SERIALIZATION.md` §9), unlike ``chart_data``.

        Raises:
            ContractViolationError: ``table``/``fmt`` is not one of the
                Protocol's own supported values -- structurally unreachable
                through any real caller, so a violation here means a caller
                broke the Protocol's own contract, a programmer error.
        """
        run = self._c.runs_store.get_run(run_id)
        context = self._build_export_context(run)
        if table == _TABLE_SUMMARY:
            return self._serialize_summary(run_id, context, fmt)
        if table == _TABLE_DETAILS:
            return self._serialize_details(run_id, context, fmt)
        raise ContractViolationError(message=f"unsupported export table: {table!r}")

    def _build_export_context(self, run: BenchmarkRun) -> RunExportContext:
        return RunExportContext(
            run_id=run.run_id,
            effective_run_name=_effective_run_name(run),
            run_mode=run.run_mode,
            exported_at=self._c.clock.now_utc(),
            app_version=_APP_VERSION,
        )

    def _serialize_summary(self, run_id: RunId, context: RunExportContext, fmt: str) -> str:
        results = self._c.results_store.list_results(run_id)
        request = SummarySerializationRequest(context=context, rows=_build_summary_rows(results))
        if fmt == "csv":
            return self._c.serializer.serialize_summary_csv(request)
        if fmt == "md":
            return self._c.serializer.serialize_summary_markdown(request)
        raise ContractViolationError(message=f"unsupported export format: {fmt!r}")

    def _serialize_details(self, run_id: RunId, context: RunExportContext, fmt: str) -> str:
        results = self._c.results_store.list_results(run_id)
        tasks_by_id = {task.task_id: task for task in self._c.tasks_store.list_tasks(run_id)}
        request = DetailsSerializationRequest(
            context=context, results=results, tasks_by_id=tasks_by_id
        )
        if fmt == "csv":
            return self._c.serializer.serialize_details_csv(request)
        if fmt == "md":
            return self._c.serializer.serialize_details_markdown(request)
        raise ContractViolationError(message=f"unsupported export format: {fmt!r}")

    def regenerate_run_analysis(
        self,
        run_id: RunId,
        provider_id: ProviderId,
        model_name: ModelName,
        *,
        on_complete: Callable[[JudgeAnalysisGenerationResult], None],
    ) -> bool:
        """Attempt to acquire ``JUDGE_ANALYSIS`` and dispatch run-analysis generation.

        Returns ``True`` immediately once the worker submission has been made
        (STORY-108-AC-2); returns ``False`` without dispatching and without ever
        calling ``on_complete`` when this gateway's own fast pre-check finds the
        gate already busy (STORY-108-AC-3). See this module's docstring for why
        that pre-check is not itself a held lease.
        """
        if self._c.gate.is_busy():
            return False
        relay = _AnalysisCompletionRelay(on_complete, on_delivered=self._pending_relays.discard)
        self._pending_relays.add(relay)
        token: CancellationToken = make_cancellation_token(clock=self._c.clock)
        future = self._c.task_runner.submit(
            functools.partial(self._c.run_analysis.generate, run_id, provider_id, model_name),
            token=token,
        )
        future.add_done_callback(
            functools.partial(self._on_analysis_done, provider_id=provider_id, relay=relay)
        )
        return True

    def _on_analysis_done(
        self,
        future: Future[object],
        *,
        provider_id: ProviderId,
        relay: _AnalysisCompletionRelay,
    ) -> None:
        analysis_result = cast("RunAnalysisResult", future.result())
        relay.deliver(self._translate_analysis_result(analysis_result, provider_id=provider_id))

    def _translate_analysis_result(
        self, result: RunAnalysisResult, *, provider_id: ProviderId
    ) -> JudgeAnalysisGenerationResult:
        provider_name = None
        if result.outcome == RunAnalysisOutcome.GENERATED:
            provider_name = self._resolve_provider_display_name(provider_id)
        return JudgeAnalysisGenerationResult(
            outcome=JudgeAnalysisGenerationOutcome(result.outcome.value),
            run_analysis_markdown=result.run_analysis_markdown,
            error_message=result.error_message,
            is_regeneration=result.is_regeneration,
            provider_name=provider_name,
        )

    def _resolve_provider_display_name(self, provider_id: ProviderId) -> str | None:
        for provider in self._c.provider_registry.list_enabled():
            if provider.provider_id == provider_id:
                return provider.name
        return None
