"""The concrete ``ResumeGateway`` implementation (STORY-109).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.3 (``ResumeGateway``), §7b (UI adapter gateways, D-R-06), §4 (the threading
contract); ``docs/v3_specification/11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md``
§8 (error handling); ``ui/resume_benchmark/protocols.py`` (the widget-side Protocol
this class satisfies structurally).

``detect_drift`` refreshes readiness, then assembles ``RunDriftDetectionInputs`` and
calls ``RunDriftDetector.detect`` (`backend/run_drift/`), which never raises (spec §8).
This gateway preserves that contract at its own boundary: a per-provider
``list_models()`` failure is caught individually (via ``AppError`` -- the
``ProviderError`` mixin `08-E` §10 documents on ``list_models`` is a non-exception
marker, never itself catchable; every real leaf it tags is also an ``AppError``
subclass) so one unreachable/misbehaving provider never aborts drift detection for
the rest -- its ``live_models`` entry is simply an empty tuple, exactly like a
provider the fresh readiness snapshot already reports unreachable.

``detect_drift``'s ``live_providers`` catalog comes from ``ProvidersStore.list_providers()``
(every configured provider, enabled or not) rather than
``ProviderRegistry.list_enabled()``. The provider-drift check
(`backend/run_drift/_internal/provider_check.py`) itself branches on a live entry's own
``enabled`` flag to tell ``PROVIDER_REMOVED`` (no live entry at all) apart from
``PROVIDER_NOW_DISABLED`` (a live entry exists but ``enabled is False``) -- passing only
the enabled subset would make the disabled row indistinguishable from a removed one and
the ``PROVIDER_NOW_DISABLED`` warning permanently unreachable. ``ProviderRegistry`` is
still used for ``get_client(...)`` when fetching each reachable provider's model list.

``serialize_table`` mirrors ``_ResultGateway.serialize_table``'s shape
(``adapters/ui_gateways/_internal/result/gateway.py``) but is not a shared import: this
module's row-aggregation helpers are its own small copies, kept module-private and never
imported cross-package -- see that module's own docstring for the same discipline. This
gateway's ``fmt`` token is ``"markdown"`` (not ``"md"``), matching
``ui.resume_benchmark.protocols.ResumeGateway.serialize_table``'s own documented
vocabulary.
"""

from collections.abc import Iterable
from importlib.metadata import PackageNotFoundError, version as _package_version
import os
from typing import Final

from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi
from ollama_llm_bench.backend.csv_export import (
    DetailsSerializationRequest,
    RunExportContext,
    SummaryRow,
    SummarySerializationRequest,
    TableSerializer,
)
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ModelName,
    ProviderId,
    ResultId,
    ResultPatch,
    ResultStatus,
    RunId,
    RunStatusPatch,
    SettingKey,
    Verdict,
)
from ollama_llm_bench.backend.errors import AppError, ContractViolationError
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.persistence.providers import ProvidersStore
from ollama_llm_bench.backend.persistence.results import ResultsStore
from ollama_llm_bench.backend.persistence.runs import RunsStore
from ollama_llm_bench.backend.persistence.tasks import TasksStore
from ollama_llm_bench.backend.provider_registry import ProviderRegistry
from ollama_llm_bench.backend.readiness import ReadinessService
from ollama_llm_bench.backend.run_drift import (
    DriftWarning,
    RunDriftDetectionInputs,
    RunDriftDetector,
)

__all__: list[str] = [
    "ResumeGatewayCollaborators",
    "_ResumeGateway",
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
_MS_PER_SECOND: Final[int] = 1000
_TABLE_SUMMARY: Final[str] = "summary"
_TABLE_DETAILS: Final[str] = "details"
_KEY_SORT_COLUMN: Final[SettingKey] = "ui.resume_sort_column"
_KEY_SORT_DESCENDING: Final[SettingKey] = "ui.resume_sort_descending"
_DEFAULT_SORT_COLUMN: Final[str] = "started"
_DEFAULT_SORT_DESCENDING: Final[bool] = True


def _read_app_version() -> str:
    """Read this application's own distribution version (§5, `05_EXPORT_FORMATS.md`).

    Mirrors ``_internal/result/gateway.py``'s identically-named helper -- see that
    module's docstring for why ``importlib.metadata`` is the mechanism.
    """
    try:
        return _package_version("ollama-llm-bench")
    except PackageNotFoundError:
        return "0.0.0"


_APP_VERSION: Final[str] = _read_app_version()


def _effective_run_name(run: BenchmarkRun) -> str:
    """Best-effort display name for the export header (mirrors the Result gateway's copy)."""
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

    Mirrors ``_ResultGateway``'s identically-named helper: groups preserve first-seen
    order, and ``provider_name`` is always the group's own snapshot name (DD-33).
    """
    groups: dict[tuple[str, str], list[BenchmarkResult]] = {}
    for result in results:
        groups.setdefault((result.provider_id, result.model_name), []).append(result)
    return tuple(_summarize_group(rows) for rows in groups.values())


def _parse_bool_setting(raw: str | None, *, default: bool) -> bool:
    """Parse a persisted ``"true"``/``"false"`` setting string, defaulting when unset."""
    if raw is None:
        return default
    return raw.strip().lower() == "true"


class ResumeGatewayCollaborators:
    """Groups the concrete gateway's constructor dependencies (<=4-parameter rule).

    A plain, private-implementation-detail bundle -- not a cross-boundary DTO, so
    it is an ordinary class rather than a ``msgspec.Struct``; it never leaves this
    ``_internal`` package.
    """

    def __init__(  # noqa: PLR0913  # this class exists solely to bundle these eleven
        # distinct required collaborators (<=4-parameter rule via a dependency bundle)
        self,
        *,
        runs_store: RunsStore,
        results_store: ResultsStore,
        tasks_store: TasksStore,
        app_settings: AppSettingsStore,
        readiness: ReadinessService,
        providers_store: ProvidersStore,
        provider_registry: ProviderRegistry,
        detector: RunDriftDetector,
        flow: BenchmarkFlowApi,
        serializer: TableSerializer,
        clock: Clock,
    ) -> None:
        self.runs_store = runs_store
        self.results_store = results_store
        self.tasks_store = tasks_store
        self.app_settings = app_settings
        self.readiness = readiness
        self.providers_store = providers_store
        self.provider_registry = provider_registry
        self.detector = detector
        self.flow = flow
        self.serializer = serializer
        self.clock = clock


class _ResumeGateway:
    """Adapter gateway for the Resume Benchmark widget, satisfying
    ``ui.resume_benchmark.protocols.ResumeGateway`` structurally (D-R-06).

    Also satisfies ``ui.common_dialogs.protocols.RenameRunGateway``,
    ``ResumeSummaryGateway``, and ``RetrySelectionGateway`` structurally with no
    extra adapter class -- proven by STORY-104-AC-2, not retested here.
    Construction is side-effect free: it performs no read, no probe, and no
    network call (STORY-109-AC-5).
    """

    def __init__(self, *, collaborators: ResumeGatewayCollaborators) -> None:
        self._c = collaborators

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        """Return every run header, newest first, for the run table."""
        return self._c.runs_store.list_runs()

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        """Load one fully-assembled run (for Clone / detail reads)."""
        return self._c.runs_store.get_run(run_id)

    def create_run(self, run: BenchmarkRun) -> RunId:
        """Create a run header + snapshots (the Clone-as-new-retry-run use case)."""
        return self._c.runs_store.create_run(run)

    def update_run_status(self, run_id: RunId, patch: RunStatusPatch) -> None:
        """Apply a run-header status/counter patch."""
        self._c.runs_store.update_run_status(run_id, patch)

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        """Set or clear a run's user-facing name."""
        self._c.runs_store.rename_run(run_id, name)

    def delete_run(self, run_id: RunId) -> None:
        """Delete a run and its dependent rows."""
        self._c.runs_store.delete_run(run_id)

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return a run's results (for counts / Clone)."""
        return self._c.results_store.list_results(run_id)

    def resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        """Return the results eligible to (re-)run on resume."""
        return self._c.results_store.list_resumable_results(run_id)

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        """Full whole-task reset of the named results to PENDING; return the count reset."""
        return self._c.results_store.reset_results(result_ids)

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        """Stage-preserving retry reset (DD-66); return the count reset."""
        return self._c.results_store.reset_results_for_retry(result_ids)

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        """Insert initial result rows (Clone-as-new-retry-run)."""
        self._c.results_store.create_results(results)

    def update_result(self, result_id: ResultId, patch: ResultPatch) -> None:
        """Apply a partial update to one result row."""
        self._c.results_store.update_result(result_id, patch)

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        """Return a run's frozen tasks (Clone)."""
        return self._c.tasks_store.list_tasks(run_id)

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        """Insert a run's frozen task snapshot (Clone-as-new-retry-run)."""
        self._c.tasks_store.create_tasks(run_id, tasks)

    def refresh_readiness(self) -> AppReadinessSnapshot:
        """Refresh the readiness snapshot before the Run Drift Detector runs."""
        return self._c.readiness.probe_all()

    def detect_drift(self, run_id: RunId) -> tuple[DriftWarning, ...]:
        """Run the Run Drift Detector fresh against the current environment.

        Blocking: refreshes readiness (fans per-provider handshakes out onto the
        worker pool and joins them, then runs the single embedding probe) before
        comparing the run's frozen snapshot -- callable only off the graphical
        thread. Never raises; every environment-availability problem, including a
        per-provider ``list_models()`` failure gathered here, is reported as a
        returned ``DriftWarning``, never an exception (11_RUN_DRIFT_DETECTOR.md §8).
        """
        run = self._c.runs_store.get_run(run_id)
        readiness = self.refresh_readiness()
        reachable_provider_ids = {
            health.provider_id for health in readiness.per_provider if health.reachable
        }
        live_providers = self._c.providers_store.list_providers()
        live_models: dict[ProviderId, tuple[ModelName, ...]] = {}
        for provider in live_providers:
            if provider.provider_id not in reachable_provider_ids:
                continue
            try:
                live_models[provider.provider_id] = self._c.provider_registry.get_client(
                    provider.provider_id
                ).list_models()
            except AppError:
                # `ProviderError` (08-E §10's documented `list_models` failure mode) is a
                # non-exception marker mixin -- see `backend.errors`'s own docstring --
                # so every real leaf it tags is caught here via its `AppError` root
                # instead. One provider's failure never aborts detection for the rest.
                live_models[provider.provider_id] = ()
        process_environment = dict(os.environ)
        resumable = self._c.results_store.list_resumable_results(run_id)
        inputs = RunDriftDetectionInputs(
            run=run,
            live_providers=live_providers,
            live_models=live_models,
            process_environment=process_environment,
            readiness=readiness,
            resumable_results=resumable,
        )
        return self._c.detector.detect(inputs)

    def get_sort_setting(self) -> tuple[str, bool]:
        """Read the persisted sort column and descending flag.

        Unset defaults to ``("started", True)`` -- no registry entry exists for
        either raw key, so this reads ``AppSettingsStore`` directly rather than
        through ``SettingsService``.
        """
        column = self._c.app_settings.get_setting(_KEY_SORT_COLUMN)
        descending_raw = self._c.app_settings.get_setting(_KEY_SORT_DESCENDING)
        return (
            column if column is not None else _DEFAULT_SORT_COLUMN,
            _parse_bool_setting(descending_raw, default=_DEFAULT_SORT_DESCENDING),
        )

    def set_sort_setting(self, column: str, descending: bool) -> None:  # noqa: FBT001  # mirrors 08-E §7b.3 verbatim
        """Persist the sort column and direction in one atomic write."""
        self._c.app_settings.upsert_settings(
            {
                _KEY_SORT_COLUMN: column,
                _KEY_SORT_DESCENDING: "true" if descending else "false",
            }
        )

    def resume_run(self, run_id: RunId) -> None:
        """Resume an INCOMPLETE run from where crash recovery left it."""
        self._c.flow.resume(run_id)

    def is_run_active(self) -> bool:
        """Whether a run is currently executing (for the per-row ``is_executing`` flag)."""
        return self._c.flow.is_running()

    def active_run_id(self) -> RunId | None:
        """The id of the currently executing run, or ``None`` when idle."""
        run = self._c.flow.current_run()
        return run.run_id if run is not None else None

    def serialize_table(self, run_id: RunId, table: str, fmt: str) -> str:
        """Produce the Summary / Details CSV or Markdown payload.

        ``table`` is ``"summary"``/``"details"``; ``fmt`` is ``"csv"``/``"markdown"``
        -- the same shared token vocabulary ``ResultGateway.serialize_table`` accepts
        (only its own ``fmt`` spelling differs: ``"md"`` there, ``"markdown"`` here,
        per each owning UI module's own Protocol).

        Raises:
            ContractViolationError: ``table``/``fmt`` is not one of the Protocol's
                own supported values -- structurally unreachable through any real
                caller, so a violation here means a caller broke the Protocol's
                own contract, a programmer error.
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
        if fmt == "markdown":
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
        if fmt == "markdown":
            return self._c.serializer.serialize_details_markdown(request)
        raise ContractViolationError(message=f"unsupported export format: {fmt!r}")
