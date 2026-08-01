"""Architecture guard + runtime proof: every concrete ``adapters/ui_gateways`` gateway is
genuinely assignable to the gateway ``Protocol`` its own widget module declares
(STORY-113-AC-2, ADR-0017).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§7b; ``docs/stories/story-113-canonical-gateway-boundary-dtos.md`` Acceptance
criteria (STORY-113-AC-2). Before STORY-113, ``ResultGateway.regenerate_run_analysis``
and six ``SettingsGateway`` methods carried a parameter/return type declared twice --
once in ``adapters/ui_gateways/protocols.py``, once again in ``ui/results/protocols.py``/
``ui/settings_dialog/models.py`` -- and because a ``msgspec.Struct``/``StrEnum`` is a
*nominal* type, those two declarations were two distinct, incompatible types. A type
checker rejected assigning the real concrete gateway to a variable annotated with the
widget-declared Protocol. STORY-113 fixed this by declaring each of those eleven record
types exactly once, in ``adapters/ui_gateways/``, and having the widget modules import
the same object. This file is the "real type-checked assignability proof" the story's
Design constraints name -- distinct from ``tests/architecture/test_gateway_implementations_
exist.py``'s (STORY-104-AC-1) purely-structural ``callable(getattr(...))`` comparison,
which cannot see a nominal-type mismatch on a shared method's parameter/return type.

The **static** proof is carried by ``mypy --strict`` checking this file: the seven widget
module Protocols are imported only under ``TYPE_CHECKING`` (this module has no runtime need
for them, and importing them unconditionally would pull the whole ``ui/*`` package tree into
a colocated-adjacent test file with no benefit) and used only as variable annotations on the
seven ``gateway: SomeGateway = make_*_gateway(...)`` bindings below -- a clean ``mypy --strict``
run over this file, with no assignment error on any of the seven bindings, IS the evidence
for STORY-113-AC-2. The **runtime** half below additionally constructs each of the seven
gateways through its real ``make_*_gateway`` factory with hand-written fake collaborators
(reusing ``tests/unit/test_common_dialog_gateway_structural_satisfaction.py``'s established
"no bare ``mocker.Mock()``" convention) and calls one representative method on each, proving
the bindings also hold at run time, not merely under static analysis.

This file lives under ``tests/architecture/`` rather than any module's colocated ``tests/``
directory because it is inherently a cross-module (``adapters`` + seven ``ui`` widget
modules) check, following ``test_result_gateway_protocol_mirrors.py``'s and
``test_gateway_implementations_exist.py``'s own precedent for the same reason -- and because
this module's own name (``tests.architecture.*``) falls outside the
``ollama_llm_bench.adapters``/``ollama_llm_bench.ui`` namespaces the import-linter "Module
internals are private" contract matches, so importing seven separate ``ui/*`` Protocol
modules together here (even only under ``TYPE_CHECKING``) is legal, unlike doing so from
production code or a colocated module test.
"""

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Final

from psygnal import Signal

from ollama_llm_bench.adapters.notification_service.testing import FakeNotificationService
from ollama_llm_bench.adapters.ui_gateways import (
    make_main_window_gateway,
    make_new_benchmark_gateway,
    make_progress_gateway,
    make_result_gateway,
    make_resume_gateway,
    make_settings_gateway,
    make_task_editor_gateway,
)
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.csv_export import (
    DetailsSerializationRequest,
    SummarySerializationRequest,
)
from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ChartData,
    ChartFilters,
    ChartKind,
    HeatmapData,
    ModelCapabilityRecord,
    ModelName,
    ProviderConfig,
    ProviderHealth,
    ProviderId,
    ProviderType,
    ReadinessState,
    RunId,
    RunMode,
    RunStatus,
    SettingKey,
)
from ollama_llm_bench.backend.import_export.testing import FakeImportExportService
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.provider_registry import LLMClient
from ollama_llm_bench.backend.run_analysis.testing import FakeRunAnalysisService
from ollama_llm_bench.backend.run_drift import DriftWarning
from ollama_llm_bench.backend.run_drift.models import RunDriftDetectionInputs
from ollama_llm_bench.backend.settings.testing import FakeSettingsService
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore
from ollama_llm_bench.backend.stores.models import RunRegistryState, WorkspaceState

if TYPE_CHECKING:
    from concurrent.futures import Future

    from ollama_llm_bench.backend.events import Subscription
    from ollama_llm_bench.ui.main_window.protocols import MainWindowGateway
    from ollama_llm_bench.ui.new_benchmark.protocols import NewBenchmarkGateway
    from ollama_llm_bench.ui.progress.protocols import ProgressGateway
    from ollama_llm_bench.ui.results.protocols import ResultGateway
    from ollama_llm_bench.ui.resume_benchmark.protocols import ResumeGateway
    from ollama_llm_bench.ui.settings_dialog.protocols import SettingsGateway
    from ollama_llm_bench.ui.task_editor.protocols import TaskEditorGateway

_RUN_ID: Final[RunId] = 42
_PROVIDER_ID: Final[ProviderId] = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME: Final[ModelName] = "llama3"


def _make_run() -> BenchmarkRun:
    return BenchmarkRun(
        run_id=_RUN_ID,
        run_name=None,
        timestamp="2026-08-01T00:00:00Z",
        run_mode=RunMode.SYNTHETIC,
        status=RunStatus.INCOMPLETE,
        total_tasks=1,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2026-08-01T00:00:00Z",
    )


def _make_snapshot() -> AppReadinessSnapshot:
    return AppReadinessSnapshot(
        overall=ReadinessState.READY, per_provider=(), embedding_reachable=True
    )


def _make_provider() -> ProviderConfig:
    return ProviderConfig(
        provider_id=_PROVIDER_ID,
        name="Ollama (local)",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
    )


# -- reusable trivial-return fakes (full Protocol surface, minimal behaviour) -------------
#
# None of these fakes need call-recording precision: this file's job is one representative
# call per gateway (proving the binding also holds at run time), not each gateway's
# exhaustive per-method wiring -- that proof already lives in each gateway's own dedicated
# colocated test file (STORY-105..111).


class _FakeAppSettingsStore:
    def get_setting(self, key: SettingKey) -> str | None:
        return None

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        return None

    def upsert_settings_in_open_transaction(self, values: dict[SettingKey, str]) -> None:
        return None

    def replace_all_settings_in_open_transaction(self, values: dict[SettingKey, str]) -> None:
        return None

    def list_settings(self) -> dict[SettingKey, str]:
        return {}

    def get_schema_version(self) -> int:
        return 1


class _FakeReadinessService:
    def snapshot(self) -> AppReadinessSnapshot:
        return _make_snapshot()

    def probe_all(self) -> AppReadinessSnapshot:
        return _make_snapshot()

    def probe(self, provider_id: ProviderId) -> ProviderHealth:
        raise NotImplementedError

    def record_embedding_capability_result(self, *, reachable: bool) -> None:
        return None


class _FakeBenchmarkFlowApi:
    def start(self, request: object) -> RunId:
        raise NotImplementedError

    def resume(self, run_id: RunId) -> None:
        raise NotImplementedError

    def pause(self) -> None:
        return None

    def resume_paused(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def shutdown(self, timeout_ms: int) -> None:
        return None

    def is_running(self) -> bool:
        return False

    def current_run(self) -> BenchmarkRun | None:
        return None


class _FakeRunDispatcher:
    def submit(self, fn: object) -> None:
        raise NotImplementedError

    def shutdown(self, timeout_ms: int) -> None:
        return None


class _FakeProviderRegistry:
    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        return ()

    def get_client(self, provider_id: ProviderId) -> LLMClient:
        raise NotImplementedError

    def reload(self) -> None:
        raise NotImplementedError


class _FakeRunsStore:
    def __init__(self, *, runs: tuple[BenchmarkRun, ...] = (_make_run(),)) -> None:
        self._runs = runs

    def create_run(self, run: BenchmarkRun) -> RunId:
        raise NotImplementedError

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        return self._runs[0]

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        return self._runs

    def update_run_status(self, run_id: RunId, patch: object) -> None:
        raise NotImplementedError

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        raise NotImplementedError

    def delete_run(self, run_id: RunId) -> None:
        raise NotImplementedError


class _FakeTasksStore:
    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        return None

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        return ()


class _FakeChartAggregator:
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
        raise NotImplementedError


class _FakeTableSerializer:
    def serialize_summary_csv(self, request: SummarySerializationRequest) -> str:
        raise NotImplementedError

    def serialize_summary_markdown(self, request: SummarySerializationRequest) -> str:
        raise NotImplementedError

    def serialize_details_csv(self, request: DetailsSerializationRequest) -> str:
        raise NotImplementedError

    def serialize_details_markdown(self, request: DetailsSerializationRequest) -> str:
        raise NotImplementedError


class _FakeClock:
    def now_utc(self) -> str:
        return "2026-08-01T00:00:00+00:00"

    def monotonic_ms(self) -> int:
        return 0


class _FakeTaskRunner:
    def submit(self, fn: Callable[[], object], *, token: CancellationToken) -> "Future[object]":
        raise NotImplementedError


class _FakeManualProviderProbeCommand:
    def probe(self) -> None:
        return None


class _FakeRunLogWriteStatus:
    def write_failed(self) -> bool:
        return False


class _FakePlatformDetector:
    @property
    def app_data_root(self) -> Path:
        return Path("/tmp/ollama-llm-bench-test")  # noqa: S108 -- never touched at runtime


class _FakeProvidersStore:
    def __init__(self, *, providers: tuple[ProviderConfig, ...] = (_make_provider(),)) -> None:
        self._providers = providers

    def list_providers(self) -> tuple[ProviderConfig, ...]:
        return self._providers

    def get_by_name(self, name: str) -> ProviderConfig | None:
        raise NotImplementedError

    def add(self, draft: object) -> ProviderId:
        raise NotImplementedError

    def update(self, provider_id: ProviderId, config: ProviderConfig) -> None:
        raise NotImplementedError

    def delete(self, provider_id: ProviderId) -> None:
        raise NotImplementedError

    def replace_providers(self, configs: tuple[ProviderConfig, ...]) -> None:
        raise NotImplementedError

    def replace_providers_in_open_transaction(self, configs: tuple[ProviderConfig, ...]) -> None:
        raise NotImplementedError


class _FakeModelCapabilitiesStore:
    def list_model_capabilities(
        self, provider_id: ProviderId, model_name: ModelName
    ) -> tuple[ModelCapabilityRecord, ...]:
        raise NotImplementedError

    def upsert_model_capability(self, record: ModelCapabilityRecord) -> None:
        raise NotImplementedError


class _FakeSettingsAtomicWriter:
    def save_all(
        self, *, providers: tuple[ProviderConfig, ...], settings_values: dict[SettingKey, str]
    ) -> None:
        raise NotImplementedError

    def reset_to_defaults(
        self,
        *,
        bundled_providers: tuple[ProviderConfig, ...],
        all_default_settings: dict[SettingKey, str],
    ) -> None:
        raise NotImplementedError


class _FakeRunDriftDetector:
    def detect(self, inputs: RunDriftDetectionInputs, /) -> tuple[DriftWarning, ...]:
        return ()


class _FakeWorkspaceStore:
    active_workspace_changed = Signal(WorkspaceState)

    def active_workspace(self) -> str:
        return "task_editor"

    def set_active_workspace(self, name: str) -> None:
        raise NotImplementedError


class _FakeRunRegistryStore:
    active_run_changed = Signal(RunRegistryState)

    def active_run_id(self) -> RunId | None:
        return None

    def set_active_run(self, run_id: RunId | None) -> None:
        raise NotImplementedError


class _FakeActiveRunTaskPaths:
    def task_paths_for(self, run_id: RunId) -> tuple[str, ...]:
        raise NotImplementedError


class _NoopSubscription:
    def cancel(self) -> None:
        return None


class _FakeEventBus:
    """An in-memory ``EventBus`` double, only used to construct ``FakeInferenceActivityStore``."""

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> "Subscription":
        del signal_name, handler, owner
        return _NoopSubscription()

    def emit(self, signal_name: str, payload: object) -> None:
        return None


# -- STORY-113-AC-2 -------------------------------------------------------------------------


def test_main_window_gateway_is_assignable_to_its_widget_declared_protocol() -> None:
    """Proves: STORY-113-AC-2

    ``MainWindowGateway`` case. Given the concrete ``MainWindowGateway`` built through its real
    ``make_main_window_gateway`` factory with fake collaborators, bound to a variable
    annotated with ``ui.main_window.protocols.MainWindowGateway`` (checked statically by
    ``mypy --strict`` over this file), when ``get_theme()`` is called, then it returns the
    resolved theme value from the injected ``SettingsService`` unchanged.
    """
    settings = FakeSettingsService()
    gateway: MainWindowGateway = make_main_window_gateway(
        app_settings=_FakeAppSettingsStore(),
        settings=settings,
        readiness=_FakeReadinessService(),
        flow=_FakeBenchmarkFlowApi(),
        dispatcher=_FakeRunDispatcher(),
    )

    result = gateway.get_theme()

    assert result == settings.get_str("ui.theme")


def test_new_benchmark_gateway_is_assignable_to_its_widget_declared_protocol() -> None:
    """Proves: STORY-113-AC-2

    ``NewBenchmarkGateway`` case. Given the concrete ``NewBenchmarkGateway`` built through its real
    ``make_new_benchmark_gateway`` factory with fake collaborators, bound to a variable
    annotated with ``ui.new_benchmark.protocols.NewBenchmarkGateway``, when
    ``readiness_snapshot()`` is called, then it returns the injected
    ``ReadinessService``'s snapshot unchanged.
    """
    gateway: NewBenchmarkGateway = make_new_benchmark_gateway(
        app_settings=_FakeAppSettingsStore(),
        settings=FakeSettingsService(),
        provider_registry=_FakeProviderRegistry(),
        readiness=_FakeReadinessService(),
        flow=_FakeBenchmarkFlowApi(),
        notification=FakeNotificationService(),
    )

    result = gateway.readiness_snapshot()

    assert result == _make_snapshot()


def test_progress_gateway_is_assignable_to_its_widget_declared_protocol() -> None:
    """Proves: STORY-113-AC-2

    ``ProgressGateway`` case. Given the concrete ``ProgressGateway`` built through its real
    ``make_progress_gateway`` factory with fake collaborators, bound to a variable
    annotated with ``ui.progress.protocols.ProgressGateway``, when ``is_run_active()``
    is called, then it returns the injected ``BenchmarkFlowApi``'s ``is_running()``
    value unchanged.
    """
    gateway: ProgressGateway = make_progress_gateway(
        flow=_FakeBenchmarkFlowApi(),
        runs_store=_FakeRunsStore(),
        results_store=FakeResultsStore(),
        app_settings=_FakeAppSettingsStore(),
        settings=FakeSettingsService(),
        platform_detector=_FakePlatformDetector(),
        task_runner=_FakeTaskRunner(),
        clock=_FakeClock(),
        probe_command=_FakeManualProviderProbeCommand(),
        write_status=_FakeRunLogWriteStatus(),
    )

    result = gateway.is_run_active()

    assert result is False


def test_result_gateway_is_assignable_to_its_widget_declared_protocol() -> None:
    """Proves: STORY-113-AC-2

    ``ResultGateway`` case. Given the concrete ``ResultGateway`` built through its real ``make_result_gateway``
    factory with fake collaborators, bound to a variable annotated with
    ``ui.results.protocols.ResultGateway`` -- the very Protocol whose
    ``regenerate_run_analysis`` signature STORY-113 fixed -- when ``list_runs()`` is
    called, then it returns the injected ``RunsStore``'s run headers unchanged.
    """
    runs_store = _FakeRunsStore()
    gateway: ResultGateway = make_result_gateway(
        runs_store=runs_store,
        results_store=FakeResultsStore(),
        tasks_store=_FakeTasksStore(),
        app_settings=_FakeAppSettingsStore(),
        settings=FakeSettingsService(),
        run_analysis=FakeRunAnalysisService(),
        gate=FakeInferenceActivityStore(clock=_FakeClock(), event_bus=_FakeEventBus()),
        provider_registry=_FakeProviderRegistry(),
        chart=_FakeChartAggregator(),
        serializer=_FakeTableSerializer(),
        task_runner=_FakeTaskRunner(),
        clock=_FakeClock(),
    )

    result = gateway.list_runs()

    assert result == runs_store.list_runs()


def test_resume_gateway_is_assignable_to_its_widget_declared_protocol() -> None:
    """Proves: STORY-113-AC-2

    ``ResumeGateway`` case. Given the concrete ``ResumeGateway`` built through its real ``make_resume_gateway``
    factory with fake collaborators, bound to a variable annotated with
    ``ui.resume_benchmark.protocols.ResumeGateway``, when ``list_runs()`` is called,
    then it returns the injected ``RunsStore``'s run headers unchanged.
    """
    runs_store = _FakeRunsStore()
    gateway: ResumeGateway = make_resume_gateway(
        runs_store=runs_store,
        results_store=FakeResultsStore(),
        tasks_store=_FakeTasksStore(),
        app_settings=_FakeAppSettingsStore(),
        readiness=_FakeReadinessService(),
        providers_store=_FakeProvidersStore(),
        provider_registry=_FakeProviderRegistry(),
        detector=_FakeRunDriftDetector(),
        flow=_FakeBenchmarkFlowApi(),
        serializer=_FakeTableSerializer(),
        clock=_FakeClock(),
    )

    result = gateway.list_runs()

    assert result == runs_store.list_runs()


def test_settings_gateway_is_assignable_to_its_widget_declared_protocol() -> None:
    """Proves: STORY-113-AC-2

    ``SettingsGateway`` case. Given the concrete ``SettingsGateway`` built through its real
    ``make_settings_gateway`` factory with fake collaborators, bound to a variable
    annotated with ``ui.settings_dialog.protocols.SettingsGateway`` -- the very
    Protocol whose six import/export methods STORY-113 fixed -- when
    ``list_providers()`` is called, then it returns the injected ``ProvidersStore``'s
    catalog unchanged.
    """
    providers_store = _FakeProvidersStore()
    gateway: SettingsGateway = make_settings_gateway(
        providers_store=providers_store,
        app_settings_store=_FakeAppSettingsStore(),
        model_capabilities_store=_FakeModelCapabilitiesStore(),
        settings=FakeSettingsService(),
        atomic_writer=_FakeSettingsAtomicWriter(),
        provider_registry=_FakeProviderRegistry(),
        readiness=_FakeReadinessService(),
        import_export=FakeImportExportService(),
        gate=FakeInferenceActivityStore(clock=_FakeClock(), event_bus=_FakeEventBus()),
        task_runner=_FakeTaskRunner(),
        dispatcher=_FakeRunDispatcher(),
        clock=_FakeClock(),
    )

    result = gateway.list_providers()

    assert result == providers_store.list_providers()


def test_task_editor_gateway_is_assignable_to_its_widget_declared_protocol() -> None:
    """Proves: STORY-113-AC-2

    ``TaskEditorGateway`` case. Given the concrete ``TaskEditorGateway`` built through its real
    ``make_task_editor_gateway`` factory with fake collaborators, bound to a variable
    annotated with ``ui.task_editor.protocols.TaskEditorGateway``, when
    ``active_workspace()`` is called, then it returns the injected ``WorkspaceStore``'s
    value unchanged.
    """
    gateway: TaskEditorGateway = make_task_editor_gateway(
        app_settings=_FakeAppSettingsStore(),
        settings=FakeSettingsService(),
        workspace_store=_FakeWorkspaceStore(),
        run_registry=_FakeRunRegistryStore(),
        active_run_task_paths=_FakeActiveRunTaskPaths(),
    )

    result = gateway.active_workspace()

    assert result == "task_editor"
