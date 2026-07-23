"""EC-PROV-1a integration: a stuck-loading model's warmup failure trips the
circuit breaker before any task ever runs inference (STORY-075).

Drives the real pipeline (`make_benchmark_pipeline`) with `benchmark.warmup_enabled`
on and `circuit_breaker.failure_threshold=1`. A model that passed readiness but
never responds during its model-switch-boundary warmup call must surface as a
provider liveness failure at the *first* provider contact — the warmup, not a
task's own inference call — and the resulting breaker trip must skip every
task in the group as `FAILED_PROVIDER` without ever adaptive-timeout-excluding
the model (`08_Cross_Cutting/08-I_edge_cases.md` EC-PROV-1a, refined by DD-64
in `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md` §6.4/§6.9). Mirrors
`tests/integration/test_first_use_model_load_failure.py`'s harness idioms
(real `make_benchmark_pipeline`, fake stores, scripted `LLMClient`, real
clock), extended with `benchmark.warmup_enabled=true` and a
`circuit_breaker.failure_threshold=1` override so one warmup failure is
sufficient to trip the breaker deterministically.
"""

from collections.abc import Callable
from concurrent.futures import Future
from itertools import count
from typing import TYPE_CHECKING, cast

from pytest_mock import MockerFixture

if TYPE_CHECKING:
    from unittest.mock import Mock

from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi, make_benchmark_pipeline
from ollama_llm_bench.backend.concurrency.protocols import TaskRunner
from ollama_llm_bench.backend.domain.models import (
    BenchmarkRunSettingEntry,
    BenchmarkTask,
    Difficulty,
    ErrorKind,
    GateLease,
    InferenceActivity,
    ModelDescriptor,
    RequiredTerms,
    ResultStatus,
    RunMode,
    RunStartRequest,
    TaskOrigin,
)
from ollama_llm_bench.backend.embedding.protocols import EmbeddingService
from ollama_llm_bench.backend.errors import AppError, HttpTimeoutError
from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.infra import make_system_clock
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.persistence.tasks.protocols import TasksStore
from ollama_llm_bench.backend.provider_registry.protocols import LLMClient, ProviderRegistry
from ollama_llm_bench.backend.settings.protocols import RunSnapshotBuilder, SettingsService
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore

_PROVIDER_ID = "22222222-2222-4222-8222-222222222222"
_MODEL_NAME = "phi-4"
_RETRY_COUNT = 0

_BASE_SETTING_ENTRIES: tuple[BenchmarkRunSettingEntry, ...] = (
    BenchmarkRunSettingEntry(setting_key="eval.sanity_min_chars", setting_value="1"),
    BenchmarkRunSettingEntry(setting_key="eval.sanity_error_markers", setting_value=""),
    BenchmarkRunSettingEntry(
        setting_key="eval.keyword_semantic_pass_threshold", setting_value="0.8"
    ),
    BenchmarkRunSettingEntry(setting_key="eval.judge_max_completion_tokens", setting_value="512"),
    BenchmarkRunSettingEntry(setting_key="eval.judge_max_parse_retries", setting_value="2"),
    BenchmarkRunSettingEntry(
        setting_key="eval.force_judge_on_prior_failure", setting_value="false"
    ),
    BenchmarkRunSettingEntry(setting_key="benchmark.min_timeout_seconds", setting_value="1"),
    BenchmarkRunSettingEntry(setting_key="benchmark.max_timeout_seconds", setting_value="1"),
    BenchmarkRunSettingEntry(setting_key="benchmark.retry_count", setting_value=str(_RETRY_COUNT)),
    BenchmarkRunSettingEntry(
        setting_key="benchmark.consecutive_max_timeouts_to_exclude", setting_value="3"
    ),
    BenchmarkRunSettingEntry(setting_key="eval.judge_timeout_min_seconds", setting_value="20"),
    BenchmarkRunSettingEntry(setting_key="eval.judge_timeout_max_seconds", setting_value="120"),
    BenchmarkRunSettingEntry(setting_key="eval.judge_timeout_escalation_steps", setting_value="2"),
    BenchmarkRunSettingEntry(
        setting_key="eval.judge_timeout_consecutive_threshold", setting_value="3"
    ),
    BenchmarkRunSettingEntry(setting_key="circuit_breaker.enabled", setting_value="true"),
    # The failure-threshold key confirmed against `08_CIRCUIT_BREAKER.md` §7 and
    # `make_circuit_breaker`'s `_internal/parameters.py` snapshot reads:
    # `circuit_breaker.failure_threshold` (default "5"). Set to "1" here so the
    # single warmup failure alone trips the breaker deterministically.
    BenchmarkRunSettingEntry(setting_key="circuit_breaker.failure_threshold", setting_value="1"),
    BenchmarkRunSettingEntry(setting_key="circuit_breaker.cooldown_seconds", setting_value="30"),
)
"""Every `eval.*`/`benchmark.*`/`circuit_breaker.*` key the pipeline's evaluator and
stability-service construction unconditionally requires present on a run's settings
snapshot, regardless of run mode — copied from
`tests/integration/test_first_use_model_load_failure.py` with the timeout ladder
narrowed to `min=max=1` second and `circuit_breaker.failure_threshold` narrowed to
`1`, keeping this integration test's wall-clock well under its 30s budget."""


def _make_task(*, task_id: str) -> BenchmarkTask:
    """A minimal, valid `BenchmarkTask` with no grading requirements."""
    return BenchmarkTask(
        task_id=task_id,
        task_origin=TaskOrigin.FILE,
        cosine_enabled=False,
        question="What is the capital of France?",
        category="geography",
        golden_answer=None,
        difficulty=Difficulty.MEDIUM,
        required_terms=RequiredTerms(),
    )


def _make_run_start_request() -> RunStartRequest:
    """A minimal, valid TASKS-mode request naming one test target."""
    return RunStartRequest(
        run_mode=RunMode.TASKS,
        test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),),
    )


class _InlineRunDispatcher:
    """A `RunDispatcher` double that runs the submitted callable synchronously, on
    the calling thread — no real `pipeline-dispatcher` thread involved, so the run
    fully settles before `pipeline.start(...)` returns."""

    def submit(self, fn: Callable[[], None]) -> None:
        fn()

    def shutdown(self, timeout_ms: int) -> None:
        del timeout_ms


def _synchronous_submit(fn: Callable[[], object], *, token: object) -> Future[object]:
    """A minimal `TaskRunner.submit` double: runs `fn` synchronously on whatever
    thread calls it and resolves a `Future` with its outcome — copied from
    `tests/integration/test_qt_benchmark_flow.py`."""
    del token
    future: Future[object] = Future()
    try:
        result = fn()
    except BaseException as exc:  # noqa: BLE001  # captured on the Future, not swallowed
        future.set_exception(exc)
    else:
        future.set_result(result)
    return future


def _make_bool_lookup(*, warmup_enabled: bool) -> Callable[[str, object], bool]:
    """Build a `SettingsService.get_bool` stand-in keyed by setting name.

    Only `benchmark.warmup_enabled` is `True` here; every phase toggle
    (`eval.phase_keyword_enabled`, `eval.phase_cosine_enabled`,
    `eval.force_judge_on_prior_failure`) stays `False` so the run exercises
    only the INFERENCE phase — the phase the model-switch warmup gates.
    """

    def _get_bool(key: str, run: object = None) -> bool:
        del run
        if key == "benchmark.warmup_enabled":
            return warmup_enabled
        return False

    return _get_bool


def _make_pipeline(
    *, mocker: MockerFixture, load_failure: AppError
) -> tuple[BenchmarkFlowApi, FakeResultsStore, LLMClient]:
    """Wire a real pipeline over a fake `LLMClient` whose every `chat`/`chat_stream`
    call raises `load_failure` (an unloadable model that never responds), a real
    `ProviderCircuitBreaker` (via `make_circuit_breaker` inside the pipeline
    itself, from `circuit_breaker.failure_threshold=1`), an inline synchronous
    dispatcher, and a `FakeResultsStore` kept for assertions.
    """
    results_store = FakeResultsStore()

    runs_store = cast("RunsStore", mocker.Mock(spec=RunsStore))
    runs_store.create_run.side_effect = count(1)  # type: ignore[attr-defined]  # a fresh id per call

    tasks_store = cast("TasksStore", mocker.Mock(spec=TasksStore))
    tasks_store.list_tasks.return_value = (  # type: ignore[attr-defined]
        _make_task(task_id="task-1"),
        _make_task(task_id="task-2"),
    )

    inference_activity_store = cast(
        "InferenceActivityStore", mocker.Mock(spec=InferenceActivityStore)
    )
    inference_activity_store.try_acquire.return_value = GateLease(  # type: ignore[attr-defined]
        activity=InferenceActivity.BENCHMARK_RUN, lease_id=1, acquired_at=0
    )

    embedding_service = cast("EmbeddingService", mocker.Mock(spec=EmbeddingService))

    client = cast("LLMClient", mocker.Mock(spec=LLMClient))
    client.chat_stream.side_effect = load_failure  # type: ignore[attr-defined]
    client.chat.side_effect = load_failure  # type: ignore[attr-defined]

    provider_registry = cast("ProviderRegistry", mocker.Mock(spec=ProviderRegistry))
    provider_registry.list_enabled.return_value = ()  # type: ignore[attr-defined]
    provider_registry.get_client.return_value = client  # type: ignore[attr-defined]

    settings_service = cast("SettingsService", mocker.Mock(spec=SettingsService))
    settings_service.get_bool.side_effect = _make_bool_lookup(  # type: ignore[attr-defined]
        warmup_enabled=True
    )
    settings_service.get_int.return_value = _RETRY_COUNT  # type: ignore[attr-defined]

    run_snapshot_builder = cast("RunSnapshotBuilder", mocker.Mock(spec=RunSnapshotBuilder))
    run_snapshot_builder.build_snapshot.return_value = _BASE_SETTING_ENTRIES  # type: ignore[attr-defined]

    bus = cast("EventBus", mocker.Mock(spec=EventBus))
    task_runner = cast("TaskRunner[object]", mocker.Mock(spec=TaskRunner))
    task_runner.submit.side_effect = _synchronous_submit  # type: ignore[attr-defined]

    pipeline = make_benchmark_pipeline(
        results_store=results_store,
        runs_store=runs_store,
        tasks_store=tasks_store,
        inference_activity_store=inference_activity_store,
        task_runner=task_runner,
        run_dispatcher=_InlineRunDispatcher(),
        bus=bus,
        clock=make_system_clock(),
        embedding_service=embedding_service,
        provider_registry=provider_registry,
        settings_service=settings_service,
        run_snapshot_builder=run_snapshot_builder,
    )
    return pipeline, results_store, client


def test_warmup_timeout_for_unloadable_model_records_provider_failure(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-075-AC-5

    With `benchmark.warmup_enabled` on and `circuit_breaker.failure_threshold`
    at 1, a model that passed readiness but never responds fails at the
    model-switch-boundary warmup — before either of the group's two task
    rows ever attempts its own inference call (EC-PROV-1a) — and the real
    circuit breaker trips off that single warmup `HttpTimeoutError`. Because
    the breaker is per-provider and the group shares one provider, both task
    rows settle `FAILED_PROVIDER`/`PROVIDER` as breaker-skipped (no network
    call), the run still reaches a terminal status (`stop_on_provider_health_failure`
    is not read by the pipeline today, so its `false` default behaviour holds
    unconditionally), and the model is never adaptive-timeout-excluded — a
    warmup failure only ever feeds the circuit breaker, never
    `AdaptiveTimeoutService.record_timeout` (`08_CIRCUIT_BREAKER.md` §6.4/§6.9).
    """
    # Arrange
    load_failure = HttpTimeoutError(message="model 'phi-4' never responded to warmup")
    pipeline, results_store, client = _make_pipeline(mocker=mocker, load_failure=load_failure)

    # Act
    run_id = pipeline.start(_make_run_start_request())

    # Assert
    rows = results_store.list_results(run_id)
    # ...the first (and only) provider call is the warmup `chat` — no task's
    # own `chat_stream` inference call is ever reached, because the breaker
    # already trips off the warmup before either row is dispatched:
    chat_mock = cast("Mock", client.chat)
    chat_stream_mock = cast("Mock", client.chat_stream)
    assert chat_mock.call_count == 1
    assert chat_stream_mock.call_count == 0
    # ...the real breaker trips off that one warmup failure: both task rows
    # settle FAILED_PROVIDER, skipped without a network call, and the run
    # still reaches a terminal status (both rows left PENDING, not abandoned):
    assert rows[0].status is ResultStatus.FAILED_PROVIDER
    assert rows[0].error_kind is ErrorKind.PROVIDER
    assert "circuit breaker is tripped" in (rows[0].error_message or "")
    assert rows[1].status is ResultStatus.FAILED_PROVIDER
    assert rows[1].error_kind is ErrorKind.PROVIDER
    assert "circuit breaker is tripped" in (rows[1].error_message or "")
    # ...and the model was NOT adaptive-excluded: both rows already asserted
    # FAILED_PROVIDER (not FAILED_TIMEOUT) above, and neither carries
    # "excluded" messaging a timeout exclusion would produce — the warmup
    # failure fed only the breaker:
    assert "excluded" not in (rows[0].error_message or "").lower()
    assert "excluded" not in (rows[1].error_message or "").lower()
