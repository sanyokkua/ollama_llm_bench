"""Unit tests for the concrete ``ResumeGateway`` (STORY-109).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b.3, §7b, §4 (the threading contract);
``docs/v3_specification/11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md`` §8.

Collaborators are hand-written, call-recording fakes rather than
``mocker.Mock(spec=...)`` -- each gateway method hits a *different* collaborator by a
*different* method name, so a purpose-built fake lets each row assert both "the right
collaborator got the right call" and "no other collaborator/method was touched," per
this module's established test-plan convention (``test_progress_gateway.py``,
``test_result_gateway.py``). Every fake raises on a method the gateway must never call.

The three Common-Dialogs structural-satisfaction checks (``RenameRunGateway``,
``ResumeSummaryGateway``, ``RetrySelectionGateway``) are proven by STORY-104-AC-2 and
are not duplicated here.
"""

from collections.abc import Callable
from typing import Final

import pytest

from ollama_llm_bench.adapters.ui_gateways import ResumeGateway, make_resume_gateway
from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi
from ollama_llm_bench.backend.csv_export import (
    DetailsSerializationRequest,
    SummarySerializationRequest,
    TableSerializer,
)
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    Iso8601Utc,
    ModelName,
    ProviderConfig,
    ProviderHealth,
    ProviderId,
    ProviderType,
    ReadinessState,
    ResultId,
    ResultPatch,
    ResultStatus,
    RunId,
    RunMode,
    RunStatus,
    RunStatusPatch,
    SettingKey,
    TaskOrigin,
)
from ollama_llm_bench.backend.errors import ProviderBadRequestError
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.persistence.providers import ProvidersStore
from ollama_llm_bench.backend.persistence.results import ResultsStore
from ollama_llm_bench.backend.persistence.runs import RunsStore
from ollama_llm_bench.backend.persistence.tasks import TasksStore
from ollama_llm_bench.backend.provider_registry import LLMClient, ProviderRegistry
from ollama_llm_bench.backend.readiness import ReadinessService
from ollama_llm_bench.backend.run_drift import DriftKind, DriftSeverity, DriftWarning
from ollama_llm_bench.backend.run_drift.models import RunDriftDetectionInputs
from ollama_llm_bench.backend.run_drift.protocols import RunDriftDetector

_KNOWN_RUN_ID: Final[RunId] = 42
_ANOTHER_RUN_ID: Final[RunId] = 7
_REACHABLE_PROVIDER_ID: Final[ProviderId] = "11111111-1111-4111-8111-111111111111"
_UNREACHABLE_PROVIDER_ID: Final[ProviderId] = "22222222-2222-4222-8222-222222222222"
_KNOWN_MODEL: Final[ModelName] = "llama3"


# -- hand-written, call-recording fakes -------------------------------------------------


class _FakeRunsStore:
    """Records every call; each method returns its configured canned value."""

    def __init__(
        self, *, run: BenchmarkRun | None = None, runs: tuple[BenchmarkRun, ...] = ()
    ) -> None:
        self._run = run
        self._runs = runs
        self.get_run_calls: list[RunId] = []
        self.list_runs_calls = 0
        self.create_run_calls: list[BenchmarkRun] = []
        self.update_run_status_calls: list[tuple[RunId, RunStatusPatch]] = []
        self.rename_run_calls: list[tuple[RunId, str | None]] = []
        self.delete_run_calls: list[RunId] = []

    def create_run(self, run: BenchmarkRun) -> RunId:
        self.create_run_calls.append(run)
        return _ANOTHER_RUN_ID

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
        self.rename_run_calls.append((run_id, run_name))

    def delete_run(self, run_id: RunId) -> None:
        self.delete_run_calls.append(run_id)


class _FakeResultsStore:
    """Records every call; each method returns its configured canned value."""

    def __init__(
        self,
        *,
        results: tuple[BenchmarkResult, ...] = (),
        resumable: tuple[BenchmarkResult, ...] = (),
        reset_count: int = 0,
        retry_reset_count: int = 0,
    ) -> None:
        self._results = results
        self._resumable = resumable
        self._reset_count = reset_count
        self._retry_reset_count = retry_reset_count
        self.list_results_calls: list[RunId] = []
        self.list_resumable_results_calls: list[RunId] = []
        self.reset_results_calls: list[tuple[ResultId, ...]] = []
        self.reset_results_for_retry_calls: list[tuple[ResultId, ...]] = []
        self.create_results_calls: list[tuple[BenchmarkResult, ...]] = []
        self.update_result_calls: list[tuple[ResultId, ResultPatch]] = []

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        self.create_results_calls.append(results)

    def update_result(self, result_id: ResultId, patch: ResultPatch) -> None:
        self.update_result_calls.append((result_id, patch))

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        self.list_results_calls.append(run_id)
        return self._results

    def list_resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        self.list_resumable_results_calls.append(run_id)
        return self._resumable

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        self.reset_results_calls.append(result_ids)
        return self._reset_count

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        self.reset_results_for_retry_calls.append(result_ids)
        return self._retry_reset_count

    def recover_in_flight_results(self) -> int:
        raise AssertionError("ResumeGateway must never call ResultsStore.recover_in_flight_results")


class _FakeTasksStore:
    """Records every call; each method returns its configured canned value."""

    def __init__(self, *, tasks: tuple[BenchmarkTask, ...] = ()) -> None:
        self._tasks = tasks
        self.list_tasks_calls: list[RunId] = []
        self.create_tasks_calls: list[tuple[RunId, tuple[BenchmarkTask, ...]]] = []

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        self.create_tasks_calls.append((run_id, tasks))

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        self.list_tasks_calls.append(run_id)
        return self._tasks


class _FakeAppSettingsStore:
    """Records get_setting/upsert_settings calls; other methods must never fire."""

    def __init__(self, *, values: dict[SettingKey, str] | None = None) -> None:
        self._values: dict[SettingKey, str] = dict(values or {})
        self.get_setting_calls: list[SettingKey] = []
        self.upsert_settings_calls: list[dict[SettingKey, str]] = []

    def get_setting(self, key: SettingKey) -> str | None:
        self.get_setting_calls.append(key)
        return self._values.get(key)

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        self.upsert_settings_calls.append(values)

    def upsert_settings_in_open_transaction(self, values: dict[SettingKey, str]) -> None:
        raise AssertionError(
            "ResumeGateway must never call AppSettingsStore.upsert_settings_in_open_transaction"
        )

    def replace_all_settings_in_open_transaction(self, values: dict[SettingKey, str]) -> None:
        raise AssertionError(
            "ResumeGateway must never call "
            "AppSettingsStore.replace_all_settings_in_open_transaction"
        )

    def list_settings(self) -> dict[SettingKey, str]:
        raise AssertionError("ResumeGateway must never call AppSettingsStore.list_settings")

    def get_schema_version(self) -> int:
        raise AssertionError("ResumeGateway must never call AppSettingsStore.get_schema_version")


class _FakeReadinessService:
    """Records probe_all calls; snapshot/probe must never fire."""

    def __init__(self, *, snapshot: AppReadinessSnapshot) -> None:
        self._snapshot = snapshot
        self.probe_all_calls = 0

    def snapshot(self) -> AppReadinessSnapshot:
        raise AssertionError("ResumeGateway must never call ReadinessService.snapshot")

    def probe_all(self) -> AppReadinessSnapshot:
        self.probe_all_calls += 1
        return self._snapshot

    def probe(self, provider_id: ProviderId) -> ProviderHealth:
        raise AssertionError("ResumeGateway must never call ReadinessService.probe")


class _FakeLLMClient:
    """A minimal ``LLMClient`` stand-in exposing only ``list_models``."""

    def __init__(
        self, *, models: tuple[ModelName, ...] = (), error: Exception | None = None
    ) -> None:
        self._models = models
        self._error = error
        self.list_models_calls = 0

    def list_models(self) -> tuple[ModelName, ...]:
        self.list_models_calls += 1
        if self._error is not None:
            raise self._error
        return self._models


class _FakeProvidersStore:
    """Records list_providers calls; every other method must never fire."""

    def __init__(self, *, providers: tuple[ProviderConfig, ...] = ()) -> None:
        self._providers = providers
        self.list_providers_calls = 0

    def list_providers(self) -> tuple[ProviderConfig, ...]:
        self.list_providers_calls += 1
        return self._providers

    def get_by_name(self, name: str) -> ProviderConfig | None:
        raise AssertionError("ResumeGateway must never call ProvidersStore.get_by_name")

    def add(self, draft: object) -> ProviderId:
        raise AssertionError("ResumeGateway must never call ProvidersStore.add")

    def update(self, provider_id: ProviderId, config: ProviderConfig) -> None:
        raise AssertionError("ResumeGateway must never call ProvidersStore.update")

    def delete(self, provider_id: ProviderId) -> None:
        raise AssertionError("ResumeGateway must never call ProvidersStore.delete")

    def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None:
        raise AssertionError("ResumeGateway must never call ProvidersStore.replace_providers")

    def replace_providers_in_open_transaction(self, configs: tuple[ProviderConfig, ...]) -> None:
        raise AssertionError(
            "ResumeGateway must never call ProvidersStore.replace_providers_in_open_transaction"
        )


class _FakeProviderRegistry:
    """Records get_client calls; list_enabled/reload must never fire."""

    def __init__(self, *, clients: dict[ProviderId, _FakeLLMClient] | None = None) -> None:
        self._clients = clients or {}
        self.get_client_calls: list[ProviderId] = []

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        raise AssertionError("ResumeGateway must never call ProviderRegistry.list_enabled")

    def get_client(self, provider_id: ProviderId) -> LLMClient:
        self.get_client_calls.append(provider_id)
        return self._clients[provider_id]  # type: ignore[return-value]

    def reload(self) -> None:
        raise AssertionError("ResumeGateway must never call ProviderRegistry.reload")


class _FakeRunDriftDetector:
    """Records the exact ``RunDriftDetectionInputs`` received; returns a canned tuple."""

    def __init__(self, *, warnings: tuple[DriftWarning, ...] = ()) -> None:
        self._warnings = warnings
        self.detect_calls: list[RunDriftDetectionInputs] = []

    def detect(self, inputs: RunDriftDetectionInputs, /) -> tuple[DriftWarning, ...]:
        self.detect_calls.append(inputs)
        return self._warnings


class _FakeBenchmarkFlowApi:
    """Records resume/is_running/current_run calls; other methods must never fire."""

    def __init__(self, *, running: bool = False, current: BenchmarkRun | None = None) -> None:
        self.resume_calls: list[RunId] = []
        self.is_running_calls = 0
        self.current_run_calls = 0
        self._running = running
        self._current = current

    def start(self, request: object) -> RunId:
        raise AssertionError("ResumeGateway must never call BenchmarkFlowApi.start")

    def resume(self, run_id: RunId) -> None:
        self.resume_calls.append(run_id)

    def pause(self) -> None:
        raise AssertionError("ResumeGateway must never call BenchmarkFlowApi.pause")

    def resume_paused(self) -> None:
        raise AssertionError("ResumeGateway must never call BenchmarkFlowApi.resume_paused")

    def stop(self) -> None:
        raise AssertionError("ResumeGateway must never call BenchmarkFlowApi.stop")

    def shutdown(self, timeout_ms: int) -> None:
        raise AssertionError("ResumeGateway must never call BenchmarkFlowApi.shutdown")

    def is_running(self) -> bool:
        self.is_running_calls += 1
        return self._running

    def current_run(self) -> BenchmarkRun | None:
        self.current_run_calls += 1
        return self._current


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
    """A trivial fixed-time Clock."""

    def now_utc(self) -> Iso8601Utc:
        return "2026-07-30T00:00:00Z"

    def monotonic_ms(self) -> int:
        return 0


def _make_run(*, run_id: RunId = _KNOWN_RUN_ID, run_name: str | None = None) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        run_name=run_name,
        timestamp="2026-07-30T00:00:00Z",
        run_mode=RunMode.SYNTHETIC,
        status=RunStatus.INCOMPLETE,
        total_tasks=1,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2026-07-30T00:00:00Z",
    )


def _make_result(*, run_id: RunId = _KNOWN_RUN_ID, result_id: ResultId = 1) -> BenchmarkResult:
    return BenchmarkResult(
        result_id=result_id,
        run_id=run_id,
        task_id="task-1",
        provider_id=_REACHABLE_PROVIDER_ID,
        provider_name="local-ollama",
        model_name=_KNOWN_MODEL,
        status=ResultStatus.PENDING,
        created_at="2026-07-30T00:00:00Z",
    )


def _make_task(*, task_id: str = "task-1") -> BenchmarkTask:
    return BenchmarkTask(task_id=task_id, task_origin=TaskOrigin.SYNTHETIC, question="2+2?")


def _make_provider(
    *, provider_id: ProviderId = _REACHABLE_PROVIDER_ID, name: str = "local-ollama"
) -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        name=name,
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
    )


def _make_snapshot(*, per_provider: tuple[ProviderHealth, ...] = ()) -> AppReadinessSnapshot:
    return AppReadinessSnapshot(
        overall=ReadinessState.READY,
        per_provider=per_provider,
        embedding_reachable=True,
    )


def _make_health(*, provider_id: ProviderId, reachable: bool) -> ProviderHealth:
    return ProviderHealth(
        provider_id=provider_id,
        reachable=reachable,
        discovery_supported=True,
        model_count=None,
        last_probe_ms=10,
        probed_at=1700000000,
    )


def _make_gateway(  # noqa: PLR0913  # test factory forwards every constructor dependency
    *,
    runs_store: RunsStore | None = None,
    results_store: ResultsStore | None = None,
    tasks_store: TasksStore | None = None,
    app_settings: AppSettingsStore | None = None,
    readiness: ReadinessService | None = None,
    providers_store: ProvidersStore | None = None,
    provider_registry: ProviderRegistry | None = None,
    detector: RunDriftDetector | None = None,
    flow: BenchmarkFlowApi | None = None,
    serializer: TableSerializer | None = None,
    clock: object = None,
) -> ResumeGateway:
    return make_resume_gateway(
        runs_store=runs_store if runs_store is not None else _FakeRunsStore(run=_make_run()),
        results_store=results_store if results_store is not None else _FakeResultsStore(),
        tasks_store=tasks_store if tasks_store is not None else _FakeTasksStore(),
        app_settings=app_settings if app_settings is not None else _FakeAppSettingsStore(),
        readiness=readiness
        if readiness is not None
        else _FakeReadinessService(snapshot=_make_snapshot()),
        providers_store=providers_store if providers_store is not None else _FakeProvidersStore(),
        provider_registry=provider_registry
        if provider_registry is not None
        else _FakeProviderRegistry(),
        detector=detector if detector is not None else _FakeRunDriftDetector(),
        flow=flow if flow is not None else _FakeBenchmarkFlowApi(),
        serializer=serializer if serializer is not None else _FakeTableSerializer(),
        clock=clock if clock is not None else _FakeClock(),  # type: ignore[arg-type]
    )


# -- STORY-109-AC-1 -----------------------------------------------------------------------


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


def _case_create_run() -> None:
    run = _make_run()
    runs_store = _FakeRunsStore(run=run)
    gateway = _make_gateway(runs_store=runs_store)
    result = gateway.create_run(run)
    assert runs_store.create_run_calls == [run]
    assert result == _ANOTHER_RUN_ID


def _case_update_run_status() -> None:
    patch = RunStatusPatch()
    runs_store = _FakeRunsStore(run=_make_run())
    gateway = _make_gateway(runs_store=runs_store)
    gateway.update_run_status(_KNOWN_RUN_ID, patch)
    assert runs_store.update_run_status_calls == [(_KNOWN_RUN_ID, patch)]


def _case_rename_run() -> None:
    runs_store = _FakeRunsStore(run=_make_run())
    gateway = _make_gateway(runs_store=runs_store)
    gateway.rename_run(_KNOWN_RUN_ID, "my run")
    assert runs_store.rename_run_calls == [(_KNOWN_RUN_ID, "my run")]


def _case_delete_run() -> None:
    runs_store = _FakeRunsStore(run=_make_run())
    gateway = _make_gateway(runs_store=runs_store)
    gateway.delete_run(_KNOWN_RUN_ID)
    assert runs_store.delete_run_calls == [_KNOWN_RUN_ID]


def _case_list_results() -> None:
    results = (_make_result(),)
    results_store = _FakeResultsStore(results=results)
    gateway = _make_gateway(results_store=results_store)
    result = gateway.list_results(_KNOWN_RUN_ID)
    assert results_store.list_results_calls == [_KNOWN_RUN_ID]
    assert result == results


def _case_resumable_results() -> None:
    resumable = (_make_result(),)
    results_store = _FakeResultsStore(resumable=resumable)
    gateway = _make_gateway(results_store=results_store)
    result = gateway.resumable_results(_KNOWN_RUN_ID)
    assert results_store.list_resumable_results_calls == [_KNOWN_RUN_ID]
    assert result == resumable


def _case_reset_results() -> None:
    results_store = _FakeResultsStore(reset_count=3)
    gateway = _make_gateway(results_store=results_store)
    result = gateway.reset_results((1, 2, 3))
    assert results_store.reset_results_calls == [(1, 2, 3)]
    assert result == 3  # noqa: PLR2004  # the fake's own configured reset count


def _case_reset_results_for_retry() -> None:
    results_store = _FakeResultsStore(retry_reset_count=2)
    gateway = _make_gateway(results_store=results_store)
    result = gateway.reset_results_for_retry((1, 2))
    assert results_store.reset_results_for_retry_calls == [(1, 2)]
    assert result == 2  # noqa: PLR2004  # the fake's own configured retry-reset count


def _case_create_results() -> None:
    results = (_make_result(),)
    results_store = _FakeResultsStore()
    gateway = _make_gateway(results_store=results_store)
    gateway.create_results(results)
    assert results_store.create_results_calls == [results]


def _case_update_result() -> None:
    patch = ResultPatch()
    results_store = _FakeResultsStore()
    gateway = _make_gateway(results_store=results_store)
    gateway.update_result(1, patch)
    assert results_store.update_result_calls == [(1, patch)]


def _case_list_tasks() -> None:
    tasks = (_make_task(),)
    tasks_store = _FakeTasksStore(tasks=tasks)
    gateway = _make_gateway(tasks_store=tasks_store)
    result = gateway.list_tasks(_KNOWN_RUN_ID)
    assert tasks_store.list_tasks_calls == [_KNOWN_RUN_ID]
    assert result == tasks


def _case_create_tasks() -> None:
    tasks = (_make_task(),)
    tasks_store = _FakeTasksStore()
    gateway = _make_gateway(tasks_store=tasks_store)
    gateway.create_tasks(_KNOWN_RUN_ID, tasks)
    assert tasks_store.create_tasks_calls == [(_KNOWN_RUN_ID, tasks)]


def _case_refresh_readiness() -> None:
    snapshot = _make_snapshot()
    readiness = _FakeReadinessService(snapshot=snapshot)
    gateway = _make_gateway(readiness=readiness)
    result = gateway.refresh_readiness()
    assert readiness.probe_all_calls == 1
    assert result is snapshot


def _case_detect_drift() -> None:
    run = _make_run()
    runs_store = _FakeRunsStore(run=run)
    results_store = _FakeResultsStore()
    readiness = _FakeReadinessService(
        snapshot=_make_snapshot(
            per_provider=(_make_health(provider_id=_REACHABLE_PROVIDER_ID, reachable=True),)
        )
    )
    providers_store = _FakeProvidersStore(providers=(_make_provider(),))
    provider_registry = _FakeProviderRegistry(
        clients={_REACHABLE_PROVIDER_ID: _FakeLLMClient(models=(_KNOWN_MODEL,))},
    )
    warnings = (
        DriftWarning(
            kind=DriftKind.PROVIDER_NOW_DISABLED,
            severity=DriftSeverity.BLOCKING,
            headline="canned",
        ),
    )
    detector = _FakeRunDriftDetector(warnings=warnings)
    gateway = _make_gateway(
        runs_store=runs_store,
        results_store=results_store,
        readiness=readiness,
        providers_store=providers_store,
        provider_registry=provider_registry,
        detector=detector,
    )

    result = gateway.detect_drift(_KNOWN_RUN_ID)

    assert runs_store.get_run_calls == [_KNOWN_RUN_ID]
    assert readiness.probe_all_calls == 1
    assert results_store.list_resumable_results_calls == [_KNOWN_RUN_ID]
    assert len(detector.detect_calls) == 1
    assert result == warnings


def _case_get_sort_setting_unset() -> None:
    app_settings = _FakeAppSettingsStore()
    gateway = _make_gateway(app_settings=app_settings)
    result = gateway.get_sort_setting()
    assert result == ("started", True)


def _case_get_sort_setting_stored() -> None:
    app_settings = _FakeAppSettingsStore(
        values={"ui.resume_sort_column": "model", "ui.resume_sort_descending": "false"}
    )
    gateway = _make_gateway(app_settings=app_settings)
    result = gateway.get_sort_setting()
    assert result == ("model", False)


def _case_set_sort_setting() -> None:
    app_settings = _FakeAppSettingsStore()
    gateway = _make_gateway(app_settings=app_settings)
    gateway.set_sort_setting("model", False)  # noqa: FBT003  # positional per the Protocol's own signature
    assert app_settings.upsert_settings_calls == [
        {"ui.resume_sort_column": "model", "ui.resume_sort_descending": "false"}
    ]


def _case_resume_run() -> None:
    flow = _FakeBenchmarkFlowApi()
    gateway = _make_gateway(flow=flow)
    gateway.resume_run(_KNOWN_RUN_ID)
    assert flow.resume_calls == [_KNOWN_RUN_ID]


def _case_is_run_active() -> None:
    flow = _FakeBenchmarkFlowApi(running=True)
    gateway = _make_gateway(flow=flow)
    result = gateway.is_run_active()
    assert flow.is_running_calls == 1
    assert result is True


def _case_active_run_id_when_running() -> None:
    run = _make_run()
    flow = _FakeBenchmarkFlowApi(current=run)
    gateway = _make_gateway(flow=flow)
    result = gateway.active_run_id()
    assert flow.current_run_calls == 1
    assert result == run.run_id


def _case_active_run_id_when_idle() -> None:
    flow = _FakeBenchmarkFlowApi(current=None)
    gateway = _make_gateway(flow=flow)
    result = gateway.active_run_id()
    assert flow.current_run_calls == 1
    assert result is None


def _case_serialize_table() -> None:
    runs_store = _FakeRunsStore(run=_make_run())
    serializer = _FakeTableSerializer()
    gateway = _make_gateway(runs_store=runs_store, serializer=serializer)

    result = gateway.serialize_table(_KNOWN_RUN_ID, "summary", "csv")

    assert len(serializer.summary_csv_calls) == 1
    assert result == "summary,csv,payload"


_AC1_CASES: tuple[tuple[str, Callable[[], None]], ...] = (
    ("list_runs", _case_list_runs),
    ("get_run", _case_get_run),
    ("create_run", _case_create_run),
    ("update_run_status", _case_update_run_status),
    ("rename_run", _case_rename_run),
    ("delete_run", _case_delete_run),
    ("list_results", _case_list_results),
    ("resumable_results", _case_resumable_results),
    ("reset_results", _case_reset_results),
    ("reset_results_for_retry", _case_reset_results_for_retry),
    ("create_results", _case_create_results),
    ("update_result", _case_update_result),
    ("list_tasks", _case_list_tasks),
    ("create_tasks", _case_create_tasks),
    ("refresh_readiness", _case_refresh_readiness),
    ("detect_drift", _case_detect_drift),
    ("get_sort_setting_unset", _case_get_sort_setting_unset),
    ("get_sort_setting_stored", _case_get_sort_setting_stored),
    ("set_sort_setting", _case_set_sort_setting),
    ("resume_run", _case_resume_run),
    ("is_run_active", _case_is_run_active),
    ("active_run_id_running", _case_active_run_id_when_running),
    ("active_run_id_idle", _case_active_run_id_when_idle),
    ("serialize_table", _case_serialize_table),
)
_AC1_CASE_IDS = [case[0] for case in _AC1_CASES]


@pytest.mark.parametrize("case", _AC1_CASES, ids=_AC1_CASE_IDS)
def test_each_method_performs_its_backend_interaction(
    case: tuple[str, Callable[[], None]],
) -> None:
    """Proves: STORY-109-AC-1

    For each of the twenty-two ``ResumeGateway`` methods, calling it performs
    exactly the stated interaction against its injected collaborator and
    returns that collaborator's value unchanged. Table-driven (plus one extra
    row distinguishing "unset" from "stored" for ``get_sort_setting``, and one
    extra row distinguishing "running" from "idle" for ``active_run_id``),
    because the variation across rows -- which collaborator, which method name
    -- is a finite enumerable set and is the point of the criterion.
    """
    _name, run_case = case
    run_case()


# -- STORY-109-AC-2 -----------------------------------------------------------------------


def test_detect_drift_reports_warnings_and_never_raises() -> None:
    """Proves: STORY-109-AC-2

    Given a drift detector whose readiness collaborator reports one
    unreachable provider, when ``detect_drift(run_id)`` is called, then it
    returns the drift warnings the detector produced unchanged and raises no
    exception -- the unreachable provider is simply excluded from
    ``live_models`` rather than aborting detection.
    """
    run = _make_run()
    runs_store = _FakeRunsStore(run=run)
    readiness = _FakeReadinessService(
        snapshot=_make_snapshot(
            per_provider=(
                _make_health(provider_id=_REACHABLE_PROVIDER_ID, reachable=True),
                _make_health(provider_id=_UNREACHABLE_PROVIDER_ID, reachable=False),
            )
        )
    )
    providers_store = _FakeProvidersStore(
        providers=(
            _make_provider(),
            _make_provider(provider_id=_UNREACHABLE_PROVIDER_ID, name="down-provider"),
        )
    )
    provider_registry = _FakeProviderRegistry(
        clients={_REACHABLE_PROVIDER_ID: _FakeLLMClient(models=(_KNOWN_MODEL,))},
    )
    warnings = (
        DriftWarning(
            kind=DriftKind.PROVIDER_NOW_UNREACHABLE,
            severity=DriftSeverity.BLOCKING,
            provider_id=_UNREACHABLE_PROVIDER_ID,
            headline="canned unreachable warning",
        ),
    )
    detector = _FakeRunDriftDetector(warnings=warnings)
    gateway = _make_gateway(
        runs_store=runs_store,
        readiness=readiness,
        providers_store=providers_store,
        provider_registry=provider_registry,
        detector=detector,
    )

    result = gateway.detect_drift(_KNOWN_RUN_ID)

    assert result == warnings
    recorded_inputs = detector.detect_calls[0]
    assert recorded_inputs.live_models[_REACHABLE_PROVIDER_ID] == (_KNOWN_MODEL,)
    assert _UNREACHABLE_PROVIDER_ID not in recorded_inputs.live_models


def test_detect_drift_includes_disabled_providers_in_the_live_catalog() -> None:
    """Proves: STORY-109-AC-2

    Given the live provider catalog contains a provider the user has since
    disabled (still configured, ``enabled=False``), when ``detect_drift(run_id)``
    is called, then that provider's ``ProviderConfig`` -- disabled flag
    included -- reaches the detector's ``live_providers`` input unchanged.
    Sourcing the catalog from ``ProvidersStore.list_providers()`` (every
    configured provider) rather than ``ProviderRegistry.list_enabled()`` (the
    enabled subset only) is what makes this distinguishable from a removed
    provider -- the provider-drift check itself (`backend/run_drift`) is what
    tells ``PROVIDER_NOW_DISABLED`` apart from ``PROVIDER_REMOVED`` by reading
    this flag, so a gateway that only forwarded enabled providers would make
    the disabled case structurally unreachable.
    """
    run = _make_run()
    runs_store = _FakeRunsStore(run=run)
    readiness = _FakeReadinessService(snapshot=_make_snapshot())
    disabled_provider = ProviderConfig(
        provider_id=_UNREACHABLE_PROVIDER_ID,
        name="disabled-provider",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=False,
    )
    providers_store = _FakeProvidersStore(providers=(disabled_provider,))
    provider_registry = _FakeProviderRegistry()
    detector = _FakeRunDriftDetector(warnings=())
    gateway = _make_gateway(
        runs_store=runs_store,
        readiness=readiness,
        providers_store=providers_store,
        provider_registry=provider_registry,
        detector=detector,
    )

    gateway.detect_drift(_KNOWN_RUN_ID)

    recorded_inputs = detector.detect_calls[0]
    assert recorded_inputs.live_providers == (disabled_provider,)
    assert provider_registry.get_client_calls == []


def test_detect_drift_recovers_from_a_per_provider_list_models_failure() -> None:
    """Proves: STORY-109-AC-2

    Given a reachable provider whose ``list_models()`` call itself raises,
    when ``detect_drift(run_id)`` is called, then detection still completes
    and returns normally -- that one provider's failure never aborts drift
    detection for the rest, and its ``live_models`` entry degrades to an
    empty tuple.
    """
    run = _make_run()
    runs_store = _FakeRunsStore(run=run)
    readiness = _FakeReadinessService(
        snapshot=_make_snapshot(
            per_provider=(_make_health(provider_id=_REACHABLE_PROVIDER_ID, reachable=True),)
        )
    )
    failing_client = _FakeLLMClient(error=ProviderBadRequestError(message="boom"))
    providers_store = _FakeProvidersStore(providers=(_make_provider(),))
    provider_registry = _FakeProviderRegistry(
        clients={_REACHABLE_PROVIDER_ID: failing_client},
    )
    detector = _FakeRunDriftDetector(warnings=())
    gateway = _make_gateway(
        runs_store=runs_store,
        readiness=readiness,
        providers_store=providers_store,
        provider_registry=provider_registry,
        detector=detector,
    )

    result = gateway.detect_drift(_KNOWN_RUN_ID)

    assert result == ()
    recorded_inputs = detector.detect_calls[0]
    assert recorded_inputs.live_models[_REACHABLE_PROVIDER_ID] == ()
    assert failing_client.list_models_calls == 1


# -- STORY-109-AC-3 -----------------------------------------------------------------------


def _case_summary_csv() -> tuple[str, str, str]:
    return ("summary", "csv", "summary_csv_calls")


def _case_summary_markdown() -> tuple[str, str, str]:
    return ("summary", "markdown", "summary_markdown_calls")


def _case_details_csv() -> tuple[str, str, str]:
    return ("details", "csv", "details_csv_calls")


def _case_details_markdown() -> tuple[str, str, str]:
    return ("details", "markdown", "details_markdown_calls")


_AC3_CASES: tuple[tuple[str, str, str], ...] = (
    _case_summary_csv(),
    _case_summary_markdown(),
    _case_details_csv(),
    _case_details_markdown(),
)
_AC3_CASE_IDS = [f"{table}_{fmt}" for table, fmt, _attr in _AC3_CASES]


@pytest.mark.parametrize("case", _AC3_CASES, ids=_AC3_CASE_IDS)
def test_serialize_table_accepts_the_shared_token_vocabulary(
    case: tuple[str, str, str],
) -> None:
    """Proves: STORY-109-AC-3

    For each of the four ``(table, fmt)`` combinations the shared token
    vocabulary supports, ``serialize_table`` invokes exactly the matching
    ``TableSerializer`` method and returns its payload unchanged.
    """
    table, fmt, expected_attr = case
    runs_store = _FakeRunsStore(run=_make_run())
    serializer = _FakeTableSerializer()
    gateway = _make_gateway(runs_store=runs_store, serializer=serializer)

    gateway.serialize_table(_KNOWN_RUN_ID, table, fmt)

    assert len(getattr(serializer, expected_attr)) == 1


# -- STORY-109-AC-4 -----------------------------------------------------------------------


def test_retry_reset_preserves_a_judge_only_failures_response() -> None:
    """Proves: STORY-109-AC-4

    Given two selected result rows -- one a judge-only failure, one an
    inference failure -- when ``reset_results_for_retry`` is called with both
    identifiers, then the gateway passes the exact identifier tuple through
    unchanged to ``ResultsStore.reset_results_for_retry`` (the collaborator
    that actually performs the stage-preserving reset, DD-66) and returns its
    reported count unchanged.
    """
    results_store = _FakeResultsStore(retry_reset_count=2)
    gateway = _make_gateway(results_store=results_store)
    result_ids: tuple[ResultId, ...] = (101, 102)

    result = gateway.reset_results_for_retry(result_ids)

    assert results_store.reset_results_for_retry_calls == [result_ids]
    assert result == 2  # noqa: PLR2004  # the fake's own configured retry-reset count


# -- STORY-109-AC-5 -----------------------------------------------------------------------


def test_constructing_the_gateway_touches_no_collaborator() -> None:
    """Proves: STORY-109-AC-5

    Given fake runs-store, results-store, tasks-store, app-settings,
    readiness, providers-store, provider-registry, drift-detector, flow, and
    serializer collaborators that record every call, when
    ``make_resume_gateway(...)`` is called, then the factory returns a gateway
    and no method was invoked on any collaborator.
    """
    runs_store = _FakeRunsStore(run=_make_run())
    results_store = _FakeResultsStore()
    tasks_store = _FakeTasksStore()
    app_settings = _FakeAppSettingsStore()
    readiness = _FakeReadinessService(snapshot=_make_snapshot())
    providers_store = _FakeProvidersStore()
    provider_registry = _FakeProviderRegistry()
    detector = _FakeRunDriftDetector()
    flow = _FakeBenchmarkFlowApi()
    serializer = _FakeTableSerializer()
    clock = _FakeClock()

    gateway = make_resume_gateway(
        runs_store=runs_store,
        results_store=results_store,
        tasks_store=tasks_store,
        app_settings=app_settings,
        readiness=readiness,
        providers_store=providers_store,
        provider_registry=provider_registry,
        detector=detector,
        flow=flow,
        serializer=serializer,
        clock=clock,
    )

    assert gateway is not None
    assert runs_store.get_run_calls == []
    assert runs_store.list_runs_calls == 0
    assert runs_store.create_run_calls == []
    assert runs_store.update_run_status_calls == []
    assert runs_store.rename_run_calls == []
    assert runs_store.delete_run_calls == []
    assert results_store.list_results_calls == []
    assert results_store.list_resumable_results_calls == []
    assert results_store.reset_results_calls == []
    assert results_store.reset_results_for_retry_calls == []
    assert results_store.create_results_calls == []
    assert results_store.update_result_calls == []
    assert tasks_store.list_tasks_calls == []
    assert tasks_store.create_tasks_calls == []
    assert app_settings.get_setting_calls == []
    assert app_settings.upsert_settings_calls == []
    assert readiness.probe_all_calls == 0
    assert providers_store.list_providers_calls == 0
    assert provider_registry.get_client_calls == []
    assert detector.detect_calls == []
    assert flow.resume_calls == []
    assert flow.is_running_calls == 0
    assert flow.current_run_calls == 0
