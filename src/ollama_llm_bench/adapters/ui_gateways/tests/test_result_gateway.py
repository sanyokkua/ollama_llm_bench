"""Unit tests for the concrete ``ResultGateway`` (STORY-108).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.5, §7b, §4 (the threading contract);
``docs/v3_specification/11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`` §2.1, §9.

Collaborators are hand-written, call-recording fakes rather than
``mocker.Mock(spec=...)`` -- several ``ResultGateway`` methods share the same
underlying collaborator (``chart_data`` and ``serialize_table`` both read
``RunsStore.get_run``, for instance), so a purpose-built fake lets each test
assert exactly which collaborator methods fired and with what arguments,
while still raising loudly if a method the gateway must never call is hit.
This mirrors ``test_new_benchmark_gateway.py`` and ``test_progress_gateway.py``'s
established convention for this module. ``FakeRunAnalysisService`` and
``FakeInferenceActivityStore`` are reused from their owning modules'
``testing.py`` rather than hand-written, per this module's test-plan
convention (``test_new_benchmark_gateway.py`` reuses ``FakeNotificationService``
the same way).
"""

from collections.abc import Callable
from concurrent.futures import Future
import threading
from typing import Final

import msgspec
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.ui_gateways import ResultGateway, make_result_gateway
from ollama_llm_bench.adapters.ui_gateways.protocols import (
    JudgeAnalysisGenerationOutcome,
    JudgeAnalysisGenerationResult,
)
from ollama_llm_bench.backend.charts import ChartAggregator
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.csv_export import (
    DetailsSerializationRequest,
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
    InferenceActivity,
    InferenceActivityContext,
    Iso8601Utc,
    ModelName,
    ProviderConfig,
    ProviderId,
    ProviderType,
    ResultStatus,
    RunId,
    RunMode,
    RunStatus,
    RunStatusPatch,
    SettingKey,
    TaskOrigin,
)
from ollama_llm_bench.backend.events import Subscription
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.persistence.results import ResultsStore
from ollama_llm_bench.backend.persistence.runs import RunsStore
from ollama_llm_bench.backend.persistence.tasks import TasksStore
from ollama_llm_bench.backend.provider_registry import LLMClient, ProviderRegistry
from ollama_llm_bench.backend.run_analysis import RunAnalysisOutcome, RunAnalysisResult
from ollama_llm_bench.backend.run_analysis.testing import FakeRunAnalysisService
from ollama_llm_bench.backend.settings import SettingsService
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

_KEY_LAST_TAB: Final[SettingKey] = "ui.last_result_tab"
_KNOWN_RUN_ID: Final[RunId] = 42
_ANOTHER_RUN_ID: Final[RunId] = 7
_KNOWN_PROVIDER_ID: Final[ProviderId] = "11111111-1111-4111-8111-111111111111"
_KNOWN_MODEL: Final[ModelName] = "llama3"


# -- hand-written, call-recording fakes -------------------------------------------------


class _FakeRunsStore:
    """Records get_run/list_runs/update_run_status calls; other methods must never fire."""

    def __init__(
        self, *, run: BenchmarkRun | None = None, runs: tuple[BenchmarkRun, ...] = ()
    ) -> None:
        self._run = run
        self._runs = runs
        self.get_run_calls: list[RunId] = []
        self.list_runs_calls = 0
        self.update_run_status_calls: list[tuple[RunId, RunStatusPatch]] = []

    def create_run(self, run: BenchmarkRun) -> RunId:
        raise AssertionError("ResultGateway must never call RunsStore.create_run")

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        self.get_run_calls.append(run_id)
        assert self._run is not None
        return self._run

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        self.list_runs_calls += 1
        return self._runs

    def update_run_status(self, run_id: RunId, patch: RunStatusPatch) -> None:
        self.update_run_status_calls.append((run_id, patch))

    def rename_run(self, run_id: RunId, run_name: str | None) -> None:
        raise AssertionError("ResultGateway must never call RunsStore.rename_run")

    def delete_run(self, run_id: RunId) -> None:
        raise AssertionError("ResultGateway must never call RunsStore.delete_run")


class _FakeResultsStore:
    """Records list_results calls; other methods must never fire."""

    def __init__(self, *, results: tuple[BenchmarkResult, ...] = ()) -> None:
        self._results = results
        self.list_results_calls: list[RunId] = []

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        raise AssertionError("ResultGateway must never call ResultsStore.create_results")

    def update_result(self, result_id: object, patch: object) -> None:
        raise AssertionError("ResultGateway must never call ResultsStore.update_result")

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        self.list_results_calls.append(run_id)
        return self._results

    def list_resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        raise AssertionError("ResultGateway must never call ResultsStore.list_resumable_results")

    def reset_results(self, result_ids: tuple[object, ...]) -> int:
        raise AssertionError("ResultGateway must never call ResultsStore.reset_results")

    def reset_results_for_retry(self, result_ids: tuple[object, ...]) -> int:
        raise AssertionError("ResultGateway must never call ResultsStore.reset_results_for_retry")

    def recover_in_flight_results(self) -> int:
        raise AssertionError("ResultGateway must never call ResultsStore.recover_in_flight_results")


class _FakeTasksStore:
    """Records list_tasks calls; create_tasks must never fire."""

    def __init__(self, *, tasks: tuple[BenchmarkTask, ...] = ()) -> None:
        self._tasks = tasks
        self.list_tasks_calls: list[RunId] = []

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        raise AssertionError("ResultGateway must never call TasksStore.create_tasks")

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        self.list_tasks_calls.append(run_id)
        return self._tasks


class _FakeAppSettingsStore:
    """Records get_setting calls; other methods must never fire."""

    def __init__(self, *, values: dict[SettingKey, str] | None = None) -> None:
        self._values: dict[SettingKey, str] = dict(values or {})
        self.get_setting_calls: list[SettingKey] = []

    def get_setting(self, key: SettingKey) -> str | None:
        self.get_setting_calls.append(key)
        return self._values.get(key)

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        raise AssertionError("ResultGateway must never call AppSettingsStore.upsert_settings")

    def list_settings(self) -> dict[SettingKey, str]:
        raise AssertionError("ResultGateway must never call AppSettingsStore.list_settings")

    def get_schema_version(self) -> int:
        raise AssertionError("ResultGateway must never call AppSettingsStore.get_schema_version")


class _FakeSettingsService:
    """Records set/get_int calls; get_str/get_bool/get_float must never fire.

    ``get_int`` backs ``_min_sample_size``'s delegation to
    ``SettingsService.get_int`` (STORY-108 spec-conformance Fix 5) -- returns
    ``5`` (the ``eval.min_sample_size`` registry default) for any key with no
    configured override, matching the real cascade's own default-fallback
    behaviour.
    """

    _DEFAULT_INT: Final[int] = 5

    def __init__(self, *, int_values: dict[SettingKey, int] | None = None) -> None:
        self.set_calls: list[tuple[SettingKey, str]] = []
        self.get_int_calls: list[SettingKey] = []
        self._int_values: dict[SettingKey, int] = dict(int_values or {})

    def get_str(self, key: SettingKey, run: BenchmarkRun | None = None) -> str:
        raise AssertionError("ResultGateway must never call SettingsService.get_str")

    def get_bool(self, key: SettingKey, run: BenchmarkRun | None = None) -> bool:
        raise AssertionError("ResultGateway must never call SettingsService.get_bool")

    def get_int(self, key: SettingKey, run: BenchmarkRun | None = None) -> int:
        self.get_int_calls.append(key)
        return self._int_values.get(key, self._DEFAULT_INT)

    def get_float(self, key: SettingKey, run: BenchmarkRun | None = None) -> float:
        raise AssertionError("ResultGateway must never call SettingsService.get_float")

    def set(self, key: SettingKey, value: str) -> None:
        self.set_calls.append((key, value))

    def upsert(self, values: dict[SettingKey, str]) -> None:
        raise AssertionError("ResultGateway must never call SettingsService.upsert")


class _FakeProviderRegistry:
    """Records list_enabled calls; the client-routing methods must never fire."""

    def __init__(self, *, providers: tuple[ProviderConfig, ...] = ()) -> None:
        self._providers = providers
        self.list_enabled_calls = 0

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        self.list_enabled_calls += 1
        return self._providers

    def get_client(self, provider_id: ProviderId) -> LLMClient:
        raise AssertionError("ResultGateway must never call ProviderRegistry.get_client")

    def reload(self) -> None:
        raise AssertionError("ResultGateway must never call ProviderRegistry.reload")


class _FakeChartAggregator:
    """Records every compute() call's keyword arguments and calling thread id;
    returns a canned result.

    ``compute_thread_ids`` backs the Fix 2 threading regression test -- proving
    ``chart_data`` dispatches this call onto a ``TaskRunner`` worker thread
    rather than running it inline on the calling thread.
    """

    def __init__(self, *, result: ChartData | HeatmapData | None = None) -> None:
        self.next_result: ChartData | HeatmapData = result or ChartData(
            chart_kind=ChartKind.AVG_TTFT_PER_MODEL, categories=(), series=()
        )
        self.compute_calls: list[dict[str, object]] = []
        self.compute_thread_ids: list[int] = []

    def compute(  # noqa: PLR0913  # mirrors the real ChartAggregator.compute signature
        self,
        *,
        chart_kind: ChartKind,
        run_mode: RunMode,
        results: tuple[BenchmarkResult, ...],
        tasks: tuple[BenchmarkTask, ...],
        filters: ChartFilters,
        min_sample_size: int = 5,
    ) -> ChartData | HeatmapData:
        self.compute_thread_ids.append(threading.get_ident())
        self.compute_calls.append(
            {
                "chart_kind": chart_kind,
                "run_mode": run_mode,
                "results": results,
                "tasks": tasks,
                "filters": filters,
                "min_sample_size": min_sample_size,
            }
        )
        return self.next_result


class _FakeTableSerializer:
    """Records every serialization call; each method returns its own canned string."""

    def __init__(self) -> None:
        self.summary_csv_calls: list[SummarySerializationRequest] = []
        self.summary_markdown_calls: list[SummarySerializationRequest] = []
        self.details_csv_calls: list[DetailsSerializationRequest] = []
        self.details_markdown_calls: list[DetailsSerializationRequest] = []

    def serialize_summary_csv(self, request: SummarySerializationRequest) -> str:
        self.summary_csv_calls.append(request)
        return "summary,csv,payload"

    def serialize_summary_markdown(self, request: SummarySerializationRequest) -> str:
        self.summary_markdown_calls.append(request)
        return "| summary | markdown |"

    def serialize_details_csv(self, request: DetailsSerializationRequest) -> str:
        self.details_csv_calls.append(request)
        return "details,csv,payload"

    def serialize_details_markdown(self, request: DetailsSerializationRequest) -> str:
        self.details_markdown_calls.append(request)
        return "| details | markdown |"


class _FakeClock:
    """Records every read; a trivial fixed-time Clock otherwise."""

    def __init__(self) -> None:
        self.now_utc_calls = 0
        self.monotonic_ms_calls = 0

    def now_utc(self) -> Iso8601Utc:
        self.now_utc_calls += 1
        return "2026-07-30T00:00:00Z"

    def monotonic_ms(self) -> int:
        self.monotonic_ms_calls += 1
        return 0


class _NoopSubscription:
    def cancel(self) -> None:
        pass


class _FakeEventBus:
    """An in-memory EventBus double; only used to construct FakeInferenceActivityStore."""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> Subscription:
        del signal_name, handler, owner
        return _NoopSubscription()

    def emit(self, signal_name: str, payload: object) -> None:
        self.emitted.append((signal_name, payload))


class _ThreadTaskRunner:
    """Runs each submitted unit on a brand-new ``threading.Thread`` and returns an
    unresolved ``Future`` immediately -- a minimal stand-in for the real
    ``QThreadPool``-backed ``TaskRunner`` (``adapters/qt_runnables``), whose
    contract requires only "submitted work runs off the calling thread." Used
    instead of the real Qt-bound runner so this colocated adapter test needs no
    live ``QApplication`` construction of its own (``qtbot`` already supplies
    one for the tests that need it). Copied from
    ``test_progress_gateway.py``'s fake of the same name and shape.
    """

    def __init__(self) -> None:
        self.submit_calls: list[Callable[[], object]] = []

    def submit(self, fn: Callable[[], object], *, token: CancellationToken) -> "Future[object]":
        self.submit_calls.append(fn)
        future: Future[object] = Future()

        def _run() -> None:
            future.set_result(fn())

        threading.Thread(target=_run, daemon=True).start()
        return future


def _make_run(*, run_id: RunId = _KNOWN_RUN_ID, run_name: str | None = None) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        run_name=run_name,
        timestamp="2026-07-30T00:00:00Z",
        run_mode=RunMode.SYNTHETIC,
        status=RunStatus.COMPLETED,
        total_tasks=1,
        completed_tasks=1,
        total_elapsed_ms=1000,
        schema_version=1,
        created_at="2026-07-30T00:00:00Z",
    )


def _make_result(*, run_id: RunId = _KNOWN_RUN_ID) -> BenchmarkResult:
    return BenchmarkResult(
        result_id=1,
        run_id=run_id,
        task_id="task-1",
        provider_id=_KNOWN_PROVIDER_ID,
        provider_name="local-ollama",
        model_name=_KNOWN_MODEL,
        status=ResultStatus.COMPLETED,
        created_at="2026-07-30T00:00:00Z",
    )


def _make_task(*, task_id: str = "task-1") -> BenchmarkTask:
    return BenchmarkTask(task_id=task_id, task_origin=TaskOrigin.SYNTHETIC, question="2+2?")


def _make_provider(
    *, provider_id: ProviderId = _KNOWN_PROVIDER_ID, name: str = "local-ollama"
) -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        name=name,
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
    )


def _make_gateway(  # noqa: PLR0913  # test factory forwards every constructor dependency
    *,
    runs_store: RunsStore | None = None,
    results_store: ResultsStore | None = None,
    tasks_store: TasksStore | None = None,
    app_settings: AppSettingsStore | None = None,
    settings: SettingsService | None = None,
    run_analysis: object = None,
    gate: object = None,
    provider_registry: ProviderRegistry | None = None,
    chart: ChartAggregator | None = None,
    serializer: TableSerializer | None = None,
    task_runner: object = None,
    clock: object = None,
) -> ResultGateway:
    return make_result_gateway(
        runs_store=runs_store if runs_store is not None else _FakeRunsStore(run=_make_run()),
        results_store=results_store if results_store is not None else _FakeResultsStore(),
        tasks_store=tasks_store if tasks_store is not None else _FakeTasksStore(),
        app_settings=app_settings if app_settings is not None else _FakeAppSettingsStore(),
        settings=settings if settings is not None else _FakeSettingsService(),
        run_analysis=run_analysis  # type: ignore[arg-type]
        if run_analysis is not None
        else FakeRunAnalysisService(),
        gate=gate  # type: ignore[arg-type]
        if gate is not None
        else FakeInferenceActivityStore(clock=_FakeClock(), event_bus=_FakeEventBus()),
        provider_registry=provider_registry
        if provider_registry is not None
        else _FakeProviderRegistry(),
        chart=chart if chart is not None else _FakeChartAggregator(),
        serializer=serializer if serializer is not None else _FakeTableSerializer(),
        task_runner=task_runner if task_runner is not None else _ThreadTaskRunner(),  # type: ignore[arg-type]
        clock=clock if clock is not None else _FakeClock(),  # type: ignore[arg-type]
    )


# -- STORY-108-AC-1 -----------------------------------------------------------------------


def _case_list_runs() -> None:
    runs = (_make_run(), _make_run(run_id=_ANOTHER_RUN_ID))
    runs_store = _FakeRunsStore(runs=runs)
    gateway = _make_gateway(runs_store=runs_store)

    result = gateway.list_runs()

    assert runs_store.list_runs_calls == 1
    assert result == runs


def _case_get_run() -> None:
    run = _make_run()
    runs_store = _FakeRunsStore(run=run)
    gateway = _make_gateway(runs_store=runs_store)

    result = gateway.get_run(_KNOWN_RUN_ID)

    assert runs_store.get_run_calls == [_KNOWN_RUN_ID]
    assert result is run


def _case_persist_run_analysis() -> None:
    runs_store = _FakeRunsStore(run=_make_run())
    gateway = _make_gateway(runs_store=runs_store)
    patch = RunStatusPatch(run_analysis="a fresh narrative")

    gateway.persist_run_analysis(_KNOWN_RUN_ID, patch)

    assert runs_store.update_run_status_calls == [(_KNOWN_RUN_ID, patch)]


def _case_list_results() -> None:
    results = (_make_result(),)
    results_store = _FakeResultsStore(results=results)
    gateway = _make_gateway(results_store=results_store)

    result = gateway.list_results(_KNOWN_RUN_ID)

    assert results_store.list_results_calls == [_KNOWN_RUN_ID]
    assert result == results


def _case_list_tasks() -> None:
    tasks = (_make_task(),)
    tasks_store = _FakeTasksStore(tasks=tasks)
    gateway = _make_gateway(tasks_store=tasks_store)

    result = gateway.list_tasks(_KNOWN_RUN_ID)

    assert tasks_store.list_tasks_calls == [_KNOWN_RUN_ID]
    assert result == tasks


def _case_get_setting_returns_none_when_unset() -> None:
    app_settings = _FakeAppSettingsStore()
    gateway = _make_gateway(app_settings=app_settings)

    result = gateway.get_setting(_KEY_LAST_TAB)

    assert app_settings.get_setting_calls == [_KEY_LAST_TAB]
    assert result is None


def _case_get_setting_returns_the_stored_value_unchanged() -> None:
    app_settings = _FakeAppSettingsStore(values={_KEY_LAST_TAB: "charts"})
    gateway = _make_gateway(app_settings=app_settings)

    result = gateway.get_setting(_KEY_LAST_TAB)

    assert result == "charts"


def _case_set_setting() -> None:
    settings = _FakeSettingsService()
    gateway = _make_gateway(settings=settings)

    gateway.set_setting(_KEY_LAST_TAB, "details")

    assert settings.set_calls == [(_KEY_LAST_TAB, "details")]


def _case_chart_data() -> None:
    run = _make_run()
    results = (_make_result(),)
    tasks = (_make_task(),)
    runs_store = _FakeRunsStore(run=run)
    results_store = _FakeResultsStore(results=results)
    tasks_store = _FakeTasksStore(tasks=tasks)
    chart = _FakeChartAggregator()
    gateway = _make_gateway(
        runs_store=runs_store, results_store=results_store, tasks_store=tasks_store, chart=chart
    )

    result = gateway.chart_data(_KNOWN_RUN_ID, ChartKind.AVG_TTFT_PER_MODEL)

    assert chart.compute_calls == [
        {
            "chart_kind": ChartKind.AVG_TTFT_PER_MODEL,
            "run_mode": run.run_mode,
            "results": results,
            "tasks": tasks,
            "filters": ChartFilters(),
            "min_sample_size": 5,
        }
    ]
    assert result is chart.next_result


def _case_serialize_table() -> None:
    """Uses ``"summary"`` -- the lowercase tab-id token the one real caller
    (``ui/results/_internal/footer.py``'s ``_active_tab``) actually sends, not
    the capitalised ``ExportKind`` enum spelling no real caller produces."""
    run = _make_run()
    results = (_make_result(),)
    runs_store = _FakeRunsStore(run=run)
    results_store = _FakeResultsStore(results=results)
    serializer = _FakeTableSerializer()
    gateway = _make_gateway(
        runs_store=runs_store, results_store=results_store, serializer=serializer
    )

    result = gateway.serialize_table(_KNOWN_RUN_ID, "summary", "csv")

    assert len(serializer.summary_csv_calls) == 1
    assert serializer.summary_csv_calls[0].context.run_id == _KNOWN_RUN_ID
    assert serializer.summary_markdown_calls == []
    assert serializer.details_csv_calls == []
    assert result == "summary,csv,payload"


def _case_serialize_table_details() -> None:
    """Exercises the other real-caller table token (``"details"``), the
    regression this module's own AC-1 case previously let slip through --
    ``_case_serialize_table`` alone only ever proved the ``"Summary"``
    (capitalised, never-sent) spelling worked, not the actual ``"summary"``/
    ``"details"`` vocabulary ``footer.py`` sends."""
    run = _make_run()
    results = (_make_result(),)
    tasks = (_make_task(),)
    runs_store = _FakeRunsStore(run=run)
    results_store = _FakeResultsStore(results=results)
    tasks_store = _FakeTasksStore(tasks=tasks)
    serializer = _FakeTableSerializer()
    gateway = _make_gateway(
        runs_store=runs_store,
        results_store=results_store,
        tasks_store=tasks_store,
        serializer=serializer,
    )

    result = gateway.serialize_table(_KNOWN_RUN_ID, "details", "csv")

    assert len(serializer.details_csv_calls) == 1
    assert serializer.details_csv_calls[0].context.run_id == _KNOWN_RUN_ID
    assert serializer.details_markdown_calls == []
    assert serializer.summary_csv_calls == []
    assert result == "details,csv,payload"


_AC1_CASES: tuple[tuple[str, Callable[[], None]], ...] = (
    ("list_runs", _case_list_runs),
    ("get_run", _case_get_run),
    ("persist_run_analysis", _case_persist_run_analysis),
    ("list_results", _case_list_results),
    ("list_tasks", _case_list_tasks),
    ("get_setting_unset", _case_get_setting_returns_none_when_unset),
    ("get_setting_stored", _case_get_setting_returns_the_stored_value_unchanged),
    ("set_setting", _case_set_setting),
    ("chart_data", _case_chart_data),
    ("serialize_table", _case_serialize_table),
    ("serialize_table_details", _case_serialize_table_details),
)
_AC1_CASE_IDS = [case[0] for case in _AC1_CASES]


@pytest.mark.parametrize("case", _AC1_CASES, ids=_AC1_CASE_IDS)
def test_each_method_performs_its_backend_interaction(
    case: tuple[str, Callable[[], None]],
) -> None:
    """Proves: STORY-108-AC-1

    For each of the nine ``ResultGateway`` methods other than
    ``regenerate_run_analysis``, calling it performs exactly the stated
    interaction against its injected collaborator and returns that
    collaborator's value unchanged. Table-driven (plus one extra row
    distinguishing "unset" from "stored" for ``get_setting``, and one extra
    row exercising ``serialize_table``'s ``"details"`` dispatch branch
    alongside its ``"summary"`` one), because the variation across rows --
    which collaborator, which method name -- is a finite enumerable set and
    is the point of the criterion.
    """
    _name, run_case = case
    run_case()


# -- STORY-108 spec-conformance Fix 2 (chart aggregation runs off the calling thread) -----


def test_chart_data_computes_on_a_worker_thread_not_the_calling_thread() -> None:
    """Proves: the spec-conformance review's Fix 2.

    ``13_CHART_AGGREGATORS.md`` §10 requires chart aggregation to run on the
    background executor and "never on the Qt UI thread." Given a real
    ``threading.Thread``-backed ``TaskRunner`` fake, when ``chart_data(...)``
    is called from this test's own thread, then ``ChartAggregator.compute``
    actually executes on a different thread than the caller -- proving the
    call is genuinely dispatched through the ``TaskRunner``, not run inline --
    while ``chart_data`` itself still returns the computed value synchronously
    (no callback, matching the Protocol's plain return-value signature).
    """
    # Arrange
    run = _make_run()
    results = (_make_result(),)
    tasks = (_make_task(),)
    runs_store = _FakeRunsStore(run=run)
    results_store = _FakeResultsStore(results=results)
    tasks_store = _FakeTasksStore(tasks=tasks)
    chart = _FakeChartAggregator()
    task_runner = _ThreadTaskRunner()
    calling_thread_id = threading.get_ident()
    gateway = _make_gateway(
        runs_store=runs_store,
        results_store=results_store,
        tasks_store=tasks_store,
        chart=chart,
        task_runner=task_runner,
    )

    # Act
    result = gateway.chart_data(_KNOWN_RUN_ID, ChartKind.AVG_TTFT_PER_MODEL)

    # Assert
    assert len(task_runner.submit_calls) == 1
    assert len(chart.compute_thread_ids) == 1
    assert chart.compute_thread_ids[0] != calling_thread_id
    assert result is chart.next_result


# -- STORY-108-AC-2 -----------------------------------------------------------------------


def test_regenerate_dispatches_to_a_worker_and_calls_back_on_the_gui_thread(
    qtbot: QtBot,
) -> None:
    """Proves: STORY-108-AC-2

    Given the single-inference gate is free, when
    ``regenerate_run_analysis(run_id, provider_id, model_name, on_complete=...)``
    is called from the graphical (test) thread, then it returns ``True``
    immediately, the run-analysis service call happens on a distinct
    ``TaskRunner`` worker thread, and ``on_complete`` is later invoked exactly
    once -- on the graphical thread, not the worker thread. The real
    ``_AnalysisCompletionRelay``/queued-signal marshalling path is exercised
    (a real ``threading.Thread``-backed ``TaskRunner`` fake, not a bypass), so
    ``qtbot`` drives a real Qt event loop to let the queued connection
    actually deliver.
    """
    # Arrange
    run_analysis = FakeRunAnalysisService()
    clock = _FakeClock()
    gate = FakeInferenceActivityStore(clock=clock, event_bus=_FakeEventBus())
    task_runner = _ThreadTaskRunner()
    gateway = _make_gateway(run_analysis=run_analysis, gate=gate, task_runner=task_runner)
    gui_thread_id = threading.get_ident()
    received: list[JudgeAnalysisGenerationResult] = []
    callback_thread_ids: list[int] = []

    def _on_complete(result: JudgeAnalysisGenerationResult) -> None:
        callback_thread_ids.append(threading.get_ident())
        received.append(result)

    # Act
    dispatched = gateway.regenerate_run_analysis(
        _KNOWN_RUN_ID, _KNOWN_PROVIDER_ID, _KNOWN_MODEL, on_complete=_on_complete
    )

    # Assert
    assert dispatched is True
    assert len(task_runner.submit_calls) == 1
    qtbot.waitUntil(lambda: len(received) == 1, timeout=2000)
    assert run_analysis.calls == [(_KNOWN_RUN_ID, _KNOWN_PROVIDER_ID, _KNOWN_MODEL)]
    assert callback_thread_ids == [gui_thread_id]


# -- STORY-108-AC-3 -----------------------------------------------------------------------


def test_regenerate_refuses_when_the_gate_is_held() -> None:
    """Proves: STORY-108-AC-3

    Given the single-inference gate is already held by another activity
    (a provider test probe, in this case -- any activity qualifies), when
    ``regenerate_run_analysis(...)`` is called, then it returns ``False``
    synchronously, the run-analysis service is never called, and
    ``on_complete`` is never invoked.
    """
    # Arrange
    clock = _FakeClock()
    gate = FakeInferenceActivityStore(clock=clock, event_bus=_FakeEventBus())
    gate.try_acquire(
        InferenceActivity.PROVIDER_TEST,
        InferenceActivityContext(activity=InferenceActivity.PROVIDER_TEST, started_at=0),
    )
    run_analysis = FakeRunAnalysisService()
    task_runner = _ThreadTaskRunner()
    gateway = _make_gateway(run_analysis=run_analysis, gate=gate, task_runner=task_runner)
    received: list[JudgeAnalysisGenerationResult] = []

    # Act
    dispatched = gateway.regenerate_run_analysis(
        _KNOWN_RUN_ID, _KNOWN_PROVIDER_ID, _KNOWN_MODEL, on_complete=received.append
    )

    # Assert
    assert dispatched is False
    assert run_analysis.calls == []
    assert received == []
    assert task_runner.submit_calls == []


# -- STORY-108-AC-4 -----------------------------------------------------------------------


def test_result_carries_the_provider_display_name_not_the_id(qtbot: QtBot) -> None:
    """Proves: STORY-108-AC-4

    Given the run-analysis service returns a ``GENERATED`` outcome for a
    provider whose display name ("My Local Ollama") differs from its
    internal UUID identifier, when the completion callback receives the
    result, then the result carries that provider's display name and no
    field on it contains the internal provider identifier.
    """
    # Arrange
    provider = _make_provider(provider_id=_KNOWN_PROVIDER_ID, name="My Local Ollama")
    provider_registry = _FakeProviderRegistry(providers=(provider,))
    run_analysis = FakeRunAnalysisService()
    run_analysis.next_result = RunAnalysisResult(
        outcome=RunAnalysisOutcome.GENERATED, run_analysis_markdown="## Overview\n\nAll good."
    )
    gate = FakeInferenceActivityStore(clock=_FakeClock(), event_bus=_FakeEventBus())
    task_runner = _ThreadTaskRunner()
    gateway = _make_gateway(
        run_analysis=run_analysis,
        gate=gate,
        provider_registry=provider_registry,
        task_runner=task_runner,
    )
    received: list[JudgeAnalysisGenerationResult] = []

    # Act
    gateway.regenerate_run_analysis(
        _KNOWN_RUN_ID, _KNOWN_PROVIDER_ID, _KNOWN_MODEL, on_complete=received.append
    )
    qtbot.waitUntil(lambda: len(received) == 1, timeout=2000)

    # Assert
    result = received[0]
    assert result.outcome == JudgeAnalysisGenerationOutcome.GENERATED
    assert result.provider_name == "My Local Ollama"
    field_values = msgspec.structs.asdict(result).values()
    serialized = "|".join(str(value) for value in field_values if value is not None)
    assert _KNOWN_PROVIDER_ID not in serialized


# -- STORY-108-AC-5 -----------------------------------------------------------------------


def test_constructing_the_gateway_touches_no_collaborator() -> None:
    """Proves: STORY-108-AC-5

    Given fake runs-store, results-store, tasks-store, settings, run-analysis,
    chart, serialiser, gate, and provider-registry collaborators that record
    every call, when ``make_result_gateway(...)`` is called, then the factory
    returns a gateway and no method was invoked on any collaborator.
    """
    # Arrange
    runs_store = _FakeRunsStore(run=_make_run())
    results_store = _FakeResultsStore()
    tasks_store = _FakeTasksStore()
    app_settings = _FakeAppSettingsStore()
    settings = _FakeSettingsService()
    run_analysis = FakeRunAnalysisService()
    clock = _FakeClock()
    event_bus = _FakeEventBus()
    gate = FakeInferenceActivityStore(clock=clock, event_bus=event_bus)
    provider_registry = _FakeProviderRegistry()
    chart = _FakeChartAggregator()
    serializer = _FakeTableSerializer()
    task_runner = _ThreadTaskRunner()

    # Act
    gateway = make_result_gateway(
        runs_store=runs_store,
        results_store=results_store,
        tasks_store=tasks_store,
        app_settings=app_settings,
        settings=settings,
        run_analysis=run_analysis,
        gate=gate,
        provider_registry=provider_registry,
        chart=chart,
        serializer=serializer,
        task_runner=task_runner,
        clock=clock,
    )

    # Assert
    assert gateway is not None
    assert runs_store.get_run_calls == []
    assert runs_store.list_runs_calls == 0
    assert runs_store.update_run_status_calls == []
    assert results_store.list_results_calls == []
    assert tasks_store.list_tasks_calls == []
    assert app_settings.get_setting_calls == []
    assert settings.set_calls == []
    assert settings.get_int_calls == []
    assert run_analysis.calls == []
    assert gate.state().current == InferenceActivity.IDLE
    assert provider_registry.list_enabled_calls == 0
    assert chart.compute_calls == []
    assert serializer.summary_csv_calls == []
    assert serializer.summary_markdown_calls == []
    assert serializer.details_csv_calls == []
    assert serializer.details_markdown_calls == []
    assert task_runner.submit_calls == []
    assert clock.now_utc_calls == 0
    assert clock.monotonic_ms_calls == 0
