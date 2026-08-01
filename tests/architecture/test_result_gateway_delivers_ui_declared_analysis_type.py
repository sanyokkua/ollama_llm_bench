"""Cross-module proof: the concrete Result gateway's ``regenerate_run_analysis`` delivers
a value that is an instance of the *widget-declared* ``JudgeAnalysisGenerationResult`` type
(STORY-113-AC-5, ADR-0017).

Source of truth: ``docs/stories/story-113-canonical-gateway-boundary-dtos.md``
Acceptance criteria (STORY-113-AC-5). The story's own Test plan names this test's
production home as the colocated ``adapters/ui_gateways/tests/test_result_gateway.py``, but
that is not possible without breaking the "Adapters never import the UI layer"
``import-linter`` contract (``pyproject.toml``'s ``[[tool.importlinter.contracts]]`` entry of
that name, ``source_modules = ["ollama_llm_bench.adapters"]``): any module under
``ollama_llm_bench.adapters.*`` -- including its own colocated ``tests/`` package, which is
still inside that namespace -- importing ``ollama_llm_bench.ui.results.protocols`` at
runtime (not merely under ``TYPE_CHECKING``, since this test needs a real ``isinstance``
check) trips that contract. The story's Design constraints are explicit that this contract
"is not to be weakened or given an ``ignore_imports`` entry for this story", so the fix is
placement, not a contract exception: this test lives under ``tests/architecture/`` instead,
following the same reasoning ``test_result_gateway_protocol_mirrors.py`` and
``test_gateway_protocol_assignability.py`` already establish for this exact class of
problem -- ``tests/architecture/*``'s own module name falls outside the
``ollama_llm_bench.adapters``/``ollama_llm_bench.ui`` namespaces the contract matches, so
importing both sides together here is legal. The Result gateway's own exhaustive
per-method wiring (STORY-108) and the other ``regenerate_run_analysis`` criteria
(STORY-108-AC-2/AC-3/AC-4) stay in the colocated ``test_result_gateway.py``, which this file
does not duplicate.
"""

from collections.abc import Callable
from concurrent.futures import Future
import threading
from typing import Final

from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.ui_gateways import make_result_gateway
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.csv_export import (
    DetailsSerializationRequest,
    SummarySerializationRequest,
)
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ChartData,
    ChartFilters,
    ChartKind,
    HeatmapData,
    Iso8601Utc,
    ModelName,
    ProviderConfig,
    ProviderId,
    RunId,
    RunMode,
    SettingKey,
)
from ollama_llm_bench.backend.events import Subscription
from ollama_llm_bench.backend.provider_registry import LLMClient
from ollama_llm_bench.backend.run_analysis.testing import FakeRunAnalysisService
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore
from ollama_llm_bench.ui.results.protocols import (
    JudgeAnalysisGenerationResult as UiJudgeAnalysisGenerationResult,
)

_KNOWN_RUN_ID: Final[RunId] = 42
_KNOWN_PROVIDER_ID: Final[ProviderId] = "11111111-1111-4111-8111-111111111111"
_KNOWN_MODEL: Final[ModelName] = "llama3"


class _FakeRunsStore:
    """Never-called stub: ``regenerate_run_analysis`` does not touch ``RunsStore``."""

    def create_run(self, run: BenchmarkRun) -> RunId:
        raise NotImplementedError

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        raise NotImplementedError

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        raise NotImplementedError

    def update_run_status(self, run_id: RunId, patch: object) -> None:
        raise NotImplementedError

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        raise NotImplementedError

    def delete_run(self, run_id: RunId) -> None:
        raise NotImplementedError


class _FakeResultsStore:
    """Never-called stub: ``regenerate_run_analysis`` does not touch ``ResultsStore``."""

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        raise NotImplementedError

    def update_result(self, result_id: object, patch: object) -> None:
        raise NotImplementedError

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        raise NotImplementedError

    def list_resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        raise NotImplementedError

    def reset_results(self, result_ids: tuple[object, ...]) -> int:
        raise NotImplementedError

    def reset_results_for_retry(self, result_ids: tuple[object, ...]) -> int:
        raise NotImplementedError

    def recover_in_flight_results(self) -> int:
        raise NotImplementedError


class _FakeTasksStore:
    """Never-called stub: ``regenerate_run_analysis`` does not touch ``TasksStore``."""

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        raise NotImplementedError

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        raise NotImplementedError


class _FakeAppSettingsStore:
    """Never-called stub: ``regenerate_run_analysis`` does not touch ``AppSettingsStore``."""

    def get_setting(self, key: SettingKey) -> str | None:
        raise NotImplementedError

    def upsert_settings(self, values: dict[SettingKey, str]) -> None:
        raise NotImplementedError

    def upsert_settings_in_open_transaction(self, values: dict[SettingKey, str]) -> None:
        raise NotImplementedError

    def replace_all_settings_in_open_transaction(self, values: dict[SettingKey, str]) -> None:
        raise NotImplementedError

    def list_settings(self) -> dict[SettingKey, str]:
        raise NotImplementedError

    def get_schema_version(self) -> int:
        raise NotImplementedError


class _FakeSettingsService:
    """Never-called stub: ``regenerate_run_analysis`` does not touch ``SettingsService``."""

    def get_str(self, key: SettingKey, run: BenchmarkRun | None = None) -> str:
        raise NotImplementedError

    def get_bool(self, key: SettingKey, run: BenchmarkRun | None = None) -> bool:
        raise NotImplementedError

    def get_int(self, key: SettingKey, run: BenchmarkRun | None = None) -> int:
        raise NotImplementedError

    def get_float(self, key: SettingKey, run: BenchmarkRun | None = None) -> float:
        raise NotImplementedError

    def set(self, key: SettingKey, value: str) -> None:
        raise NotImplementedError

    def upsert(self, values: dict[SettingKey, str]) -> None:
        raise NotImplementedError


class _FakeProviderRegistry:
    """Working fake: ``list_enabled`` returns an empty catalog, so the provider-name
    resolution loop inside ``regenerate_run_analysis`` finds nothing (the result's
    ``provider_name`` stays ``None``, which this test does not assert on)."""

    def list_enabled(self) -> tuple[ProviderConfig, ...]:
        return ()

    def get_client(self, provider_id: ProviderId) -> LLMClient:
        raise NotImplementedError

    def reload(self) -> None:
        raise NotImplementedError


class _FakeChartAggregator:
    """Never-called stub: this test never calls ``chart_data``."""

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
    """Never-called stub: this test never calls ``serialize_table``."""

    def serialize_summary_csv(self, request: SummarySerializationRequest) -> str:
        raise NotImplementedError

    def serialize_summary_markdown(self, request: SummarySerializationRequest) -> str:
        raise NotImplementedError

    def serialize_details_csv(self, request: DetailsSerializationRequest) -> str:
        raise NotImplementedError

    def serialize_details_markdown(self, request: DetailsSerializationRequest) -> str:
        raise NotImplementedError


class _FakeClock:
    """A deterministic, injectable ``Clock``."""

    def now_utc(self) -> Iso8601Utc:
        return "2026-08-01T00:00:00Z"

    def monotonic_ms(self) -> int:
        return 0


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
    ) -> Subscription:
        del signal_name, handler, owner
        return _NoopSubscription()

    def emit(self, signal_name: str, payload: object) -> None:
        return None


class _ThreadTaskRunner:
    """Runs each submitted unit on a brand-new ``threading.Thread`` and returns an
    unresolved ``Future`` immediately -- a minimal stand-in for the real
    ``QThreadPool``-backed ``TaskRunner``, copied from
    ``adapters/ui_gateways/tests/test_result_gateway.py``'s fake of the same name and
    shape."""

    def submit(self, fn: Callable[[], object], *, token: CancellationToken) -> "Future[object]":
        del token
        future: Future[object] = Future()

        def _run() -> None:
            future.set_result(fn())

        threading.Thread(target=_run, daemon=True).start()
        return future


def test_regenerate_run_analysis_delivers_the_ui_declared_result_type(qtbot: QtBot) -> None:
    """Proves: STORY-113-AC-5

    Given the run-analysis service returns a generated outcome, when the concrete
    Result gateway's ``regenerate_run_analysis`` worker settles, then the value
    delivered to ``on_complete`` is an instance of the same ``JudgeAnalysisGenerationResult``
    type ``ui/results/`` declares its callback against -- imported here from
    ``ui.results.protocols``, not ``adapters.ui_gateways`` -- proving the two names are
    genuinely the same object (STORY-113-AC-1), not merely two structurally-identical
    types. This is somewhat definitional post-STORY-113 (both imports resolve to the same
    object), but guards against a future regression that re-splits the declaration --
    exactly what ``adapters/ui_gateways/protocols.py``'s module docstring warns against.
    """
    # Arrange
    run_analysis = FakeRunAnalysisService()
    gate = FakeInferenceActivityStore(clock=_FakeClock(), event_bus=_FakeEventBus())
    task_runner = _ThreadTaskRunner()
    gateway = make_result_gateway(
        runs_store=_FakeRunsStore(),
        results_store=_FakeResultsStore(),
        tasks_store=_FakeTasksStore(),
        app_settings=_FakeAppSettingsStore(),
        settings=_FakeSettingsService(),
        run_analysis=run_analysis,
        gate=gate,
        provider_registry=_FakeProviderRegistry(),
        chart=_FakeChartAggregator(),
        serializer=_FakeTableSerializer(),
        task_runner=task_runner,
        clock=_FakeClock(),
    )
    received: list[object] = []

    # Act
    gateway.regenerate_run_analysis(
        _KNOWN_RUN_ID, _KNOWN_PROVIDER_ID, _KNOWN_MODEL, on_complete=received.append
    )
    qtbot.waitUntil(lambda: len(received) == 1, timeout=2000)

    # Assert
    assert isinstance(received[0], UiJudgeAnalysisGenerationResult)
