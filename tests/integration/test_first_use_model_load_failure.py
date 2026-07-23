"""EC-PROV-1a integration: an advertised model that cannot load fails at first use
(STORY-074).

Drives the real pipeline (`make_benchmark_pipeline`) with `benchmark.warmup_enabled`
off — the pipeline's only behaviour today, since no module anywhere reads that
setting key yet. A model that passed readiness but cannot actually load must
surface as a per-task `FAILED_*` failure the first time it is used for inference,
and the run must advance to its next task instead of aborting
(`08_Cross_Cutting/08-I_edge_cases.md` EC-PROV-1a).
"""

from collections.abc import Callable
from concurrent.futures import Future
from itertools import count
from typing import TYPE_CHECKING, NamedTuple, cast

import pytest
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
from ollama_llm_bench.backend.errors import AppError, ModelNotAvailableError, ProviderServerError
from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.infra import make_system_clock
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.persistence.tasks.protocols import TasksStore
from ollama_llm_bench.backend.provider_registry.protocols import LLMClient, ProviderRegistry
from ollama_llm_bench.backend.settings.protocols import RunSnapshotBuilder, SettingsService
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME = "phi-4"
_RETRY_COUNT = 3

_SETTING_ENTRIES: tuple[BenchmarkRunSettingEntry, ...] = (
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
    BenchmarkRunSettingEntry(setting_key="benchmark.min_timeout_seconds", setting_value="5"),
    BenchmarkRunSettingEntry(setting_key="benchmark.max_timeout_seconds", setting_value="30"),
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
    BenchmarkRunSettingEntry(setting_key="circuit_breaker.failure_threshold", setting_value="5"),
    BenchmarkRunSettingEntry(setting_key="circuit_breaker.cooldown_seconds", setting_value="30"),
)
"""Every `eval.*`/`benchmark.*`/`circuit_breaker.*` key the pipeline's evaluator and
stability-service construction unconditionally requires present on a run's settings
snapshot, regardless of run mode — copied from `tests/integration/test_qt_benchmark_flow.py`
(kept as a self-contained local copy per that module's own placement rule, outside its
colocated `tests/`)."""

_WARMUP_OFF_ENTRY = BenchmarkRunSettingEntry(
    setting_key="benchmark.warmup_enabled", setting_value="false"
)


class _ExpectedOutcome(NamedTuple):
    """One parametrized case's expected classification, message, and attempt
    count — bundled into one field so the test function stays within the
    project's 4-parameter guideline despite covering four distinct
    expectations per case."""

    status: ResultStatus
    error_kind: ErrorKind
    message_fragment: str
    chat_stream_calls: int


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


def _make_pipeline(
    *, mocker: MockerFixture, load_failure: AppError
) -> tuple[BenchmarkFlowApi, FakeResultsStore, LLMClient]:
    """Wire a real pipeline over a fake `LLMClient` whose every chat call raises
    `load_failure`, an inline synchronous dispatcher, and a `FakeResultsStore` kept
    for assertions — mirrors `tests/integration/test_qt_benchmark_flow.py`'s
    `_make_facade` wiring, except two tasks are staged (so advancement to the next
    task is observable) and the run settles synchronously via `_InlineRunDispatcher`.
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
    settings_service.get_bool.return_value = False  # type: ignore[attr-defined]
    settings_service.get_int.return_value = _RETRY_COUNT  # type: ignore[attr-defined]

    run_snapshot_builder = cast("RunSnapshotBuilder", mocker.Mock(spec=RunSnapshotBuilder))
    run_snapshot_builder.build_snapshot.return_value = (  # type: ignore[attr-defined]
        *_SETTING_ENTRIES,
        _WARMUP_OFF_ENTRY,
    )

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


@pytest.mark.parametrize(
    ("load_failure", "expected"),
    [
        pytest.param(
            ProviderServerError(message="model 'phi-4' cannot load: out of memory"),
            _ExpectedOutcome(
                status=ResultStatus.FAILED_PROVIDER,
                error_kind=ErrorKind.PROVIDER,
                message_fragment="cannot load",
                chat_stream_calls=2 * (1 + _RETRY_COUNT),
            ),
            id="transient-load-failure-exhausts-retries",
        ),
        pytest.param(
            ModelNotAvailableError(message="model 'phi-4' is not resident on the backend"),
            _ExpectedOutcome(
                status=ResultStatus.FAILED_PROVIDER,
                error_kind=ErrorKind.PROVIDER,
                message_fragment="not resident",
                chat_stream_calls=2 * 1,
            ),
            id="non-retryable-model-error",
        ),
    ],
)
def test_warmup_off_first_use_load_failure_marks_failed_and_advances(
    load_failure: AppError,
    expected: _ExpectedOutcome,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-074-AC-3

    With benchmark.warmup_enabled off, a model that passed readiness but
    cannot load fails at the first task's inference: the row settles to a
    FAILED_* status carrying the load-failure error, and the pipeline
    advances to the next task without aborting the run. The two parametrized
    load failures share the same terminal FAILED_PROVIDER/PROVIDER
    classification (ModelNotAvailableError maps there per
    `17_ERROR_TAXONOMY.md` §6.3, not FAILED_INFERENCE/LLM), so the cases are
    discriminated instead by the message they carry and by whether the
    transient failure genuinely exhausted the run's retry ladder versus the
    non-retryable failure being surfaced on its first and only attempt.
    """
    # Arrange
    pipeline, results_store, client = _make_pipeline(mocker=mocker, load_failure=load_failure)

    # Act
    run_id = pipeline.start(_make_run_start_request())

    # Assert
    rows = results_store.list_results(run_id)
    assert rows[0].status is expected.status
    assert rows[0].error_kind is expected.error_kind
    assert expected.message_fragment in (rows[0].error_message or "")
    # ...and the pipeline advanced: the second task's row also reached the same
    # terminal state rather than being abandoned PENDING by an aborted run:
    assert rows[1].status is expected.status
    # ...and the two parametrized cases genuinely diverged in behaviour: the
    # transient case retried to exhaustion (benchmark.retry_count=3 -> 4
    # attempts per task) while the non-retryable case made exactly one attempt
    # per task, across both of the run's two tasks.
    chat_stream_mock = cast("Mock", client.chat_stream)
    assert chat_stream_mock.call_count == expected.chat_stream_calls
