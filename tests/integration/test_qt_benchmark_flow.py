"""Integration tests for ``QtBenchmarkFlow`` crossing a real, persistent
``pipeline-dispatcher`` thread boundary (STORY-042-AC-1, STORY-042-AC-3).

These wire a real ``make_run_dispatcher()`` and a real ``make_benchmark_pipeline(...)``
(with fakes for the per-aggregate stores and collaborators, mirroring
``backend/benchmark_pipeline``'s own colocated fixture style) behind the facade under
test, so they belong in ``tests/integration/`` rather than the module's colocated unit
tests — a colocated unit test may only exercise the facade in isolation against a mocked
``BenchmarkFlowApi``, never a real dispatcher-thread crossing.
"""

from collections.abc import Callable, Iterator
from concurrent.futures import Future
from itertools import count
import threading
import time
from typing import cast

from pytest_mock import MockerFixture

from ollama_llm_bench.adapters.qt_benchmark_flow import (
    QtBenchmarkFlow,
    make_qt_benchmark_flow,
    make_run_dispatcher,
)
from ollama_llm_bench.backend.benchmark_pipeline import make_benchmark_pipeline
from ollama_llm_bench.backend.domain.models import (
    BenchmarkRunSettingEntry,
    BenchmarkTask,
    ChatChunk,
    ChatResponse,
    Difficulty,
    GateLease,
    InferenceActivity,
    ModelDescriptor,
    RequiredTerms,
    RunMode,
    RunStartRequest,
    TaskOrigin,
)
from ollama_llm_bench.backend.embedding.protocols import EmbeddingService
from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.infra import make_system_clock
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.persistence.tasks.protocols import TasksStore
from ollama_llm_bench.backend.provider_registry.protocols import (
    ChatStream,
    LLMClient,
    ProviderRegistry,
)
from ollama_llm_bench.backend.settings.protocols import RunSnapshotBuilder, SettingsService
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME = "llama3"
_UNIT_DELAY_S = 0.3
_WAIT_TIMEOUT_S = 5.0

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
    BenchmarkRunSettingEntry(setting_key="benchmark.retry_count", setting_value="3"),
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
snapshot, regardless of run mode — mirrors `backend/benchmark_pipeline/tests/conftest.py`'s
own fixture set (kept as a self-contained local copy per this module's placement in
`tests/integration/`, outside that module's colocated `tests/`)."""


class _StagesNoTasks:
    """A `RunTaskStager` double that stages nothing.

    This test seeds its `TasksStore` with the rows it wants the run to execute
    rather than routing them through `RunStartRequest.task_paths`, so a stager
    that returns nothing leaves that seeding untouched. Restated here rather
    than imported -- `backend/benchmark_pipeline/tests/conftest.py` has the
    same double, but the integration tier does not reach into a colocated test
    package (see this tier's own duplication convention).
    """

    def build(self, request: RunStartRequest, /) -> tuple[BenchmarkTask, ...]:
        return ()


def _make_task() -> BenchmarkTask:
    """A minimal, valid `BenchmarkTask` with no grading requirements."""
    return BenchmarkTask(
        task_id="task-1",
        task_origin=TaskOrigin.FILE,
        cosine_enabled=False,
        question="What is the capital of France?",
        category="geography",
        golden_answer=None,
        difficulty=Difficulty.MEDIUM,
        required_terms=RequiredTerms(),
    )


class _DelayedChatStream:
    """A `ChatStream` double that sleeps before yielding, so the run stays observably
    in flight for a moment after `start()` returns."""

    def __init__(self) -> None:
        self._chunks = (ChatChunk(content="Paris.", delta_tokens=3),)
        self._response = ChatResponse(
            text="Paris.", total_time_ms=10, ttft_ms=5, prompt_tokens=5, completion_tokens=3
        )

    def __iter__(self) -> Iterator[ChatChunk]:
        time.sleep(_UNIT_DELAY_S)
        return iter(self._chunks)

    def __next__(self) -> ChatChunk:  # pragma: no cover — iteration goes via __iter__
        raise StopIteration

    def trailing_response(self) -> ChatResponse:
        return self._response


def _synchronous_submit(fn: Callable[[], object], *, token: object) -> Future[object]:
    """A minimal `TaskRunner.submit` double: runs `fn` synchronously (on whatever
    thread calls it — the real dispatcher thread, in this test) and resolves a
    `Future` with its outcome. Only the `RunDispatcher` boundary is under test here,
    so the individual unit's own scheduling mechanics are deliberately inline."""
    del token
    future: Future[object] = Future()
    try:
        result = fn()
    except BaseException as exc:  # noqa: BLE001  # captured on the Future, not swallowed
        future.set_exception(exc)
    else:
        future.set_result(result)
    return future


def _make_facade(mocker: MockerFixture) -> QtBenchmarkFlow:
    """Wire a real `RunDispatcher`, a real pipeline, and the facade under test."""
    runs_store = cast("RunsStore", mocker.Mock(spec=RunsStore))
    runs_store.create_run.side_effect = count(1)  # type: ignore[attr-defined]  # a fresh id per call

    tasks_store = cast("TasksStore", mocker.Mock(spec=TasksStore))
    tasks_store.list_tasks.return_value = (_make_task(),)  # type: ignore[attr-defined]

    inference_activity_store = cast(
        "InferenceActivityStore", mocker.Mock(spec=InferenceActivityStore)
    )
    inference_activity_store.try_acquire.return_value = GateLease(  # type: ignore[attr-defined]
        activity=InferenceActivity.BENCHMARK_RUN, lease_id=1, acquired_at=0
    )

    embedding_service = cast("EmbeddingService", mocker.Mock(spec=EmbeddingService))

    client = cast("LLMClient", mocker.Mock())

    def _chat_stream(request: object, *, token: object) -> ChatStream:
        del request, token
        return _DelayedChatStream()

    client.chat_stream.side_effect = _chat_stream  # type: ignore[attr-defined]

    provider_registry = cast("ProviderRegistry", mocker.Mock(spec=ProviderRegistry))
    provider_registry.list_enabled.return_value = ()  # type: ignore[attr-defined]
    provider_registry.get_client.return_value = client  # type: ignore[attr-defined]

    settings_service = cast("SettingsService", mocker.Mock(spec=SettingsService))
    settings_service.get_bool.return_value = False  # type: ignore[attr-defined]
    settings_service.get_int.return_value = 30  # type: ignore[attr-defined]

    run_snapshot_builder = cast("RunSnapshotBuilder", mocker.Mock(spec=RunSnapshotBuilder))
    run_snapshot_builder.build_snapshot.return_value = _SETTING_ENTRIES  # type: ignore[attr-defined]

    bus = cast("EventBus", mocker.Mock(spec=EventBus))
    task_runner = mocker.Mock()
    task_runner.submit.side_effect = _synchronous_submit

    pipeline = make_benchmark_pipeline(
        results_store=FakeResultsStore(),
        runs_store=runs_store,
        tasks_store=tasks_store,
        task_stager=_StagesNoTasks(),
        inference_activity_store=inference_activity_store,
        task_runner=task_runner,
        run_dispatcher=make_run_dispatcher(),
        bus=bus,
        clock=make_system_clock(),
        embedding_service=embedding_service,
        provider_registry=provider_registry,
        settings_service=settings_service,
        run_snapshot_builder=run_snapshot_builder,
    )
    return make_qt_benchmark_flow(pipeline=pipeline)


def _make_run_start_request() -> RunStartRequest:
    """A minimal, valid TASKS-mode request naming one test target."""
    return RunStartRequest(
        run_mode=RunMode.TASKS,
        test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),),
    )


def _wait_until_idle(facade: QtBenchmarkFlow, timeout_s: float = _WAIT_TIMEOUT_S) -> None:
    """Poll `is_running()` from the test's own thread until the dispatcher settles."""
    deadline = time.monotonic() + timeout_s
    while facade.is_running() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not facade.is_running(), "the run did not settle within the timeout"


def test_start_returns_promptly_and_hands_run_to_dispatcher(mocker: MockerFixture) -> None:
    """Proves: STORY-042-AC-1

    Given the facade is constructed with a real, persistent dispatcher thread,
    when `start(request)` is called,
    then the call returns promptly with a run id (it does not block until the
    run finishes) and the run stays observably in flight — `is_running()` is
    still `True` immediately after `start()` returns — because the run
    command was handed off to the dispatcher thread rather than executed
    inline on the calling thread.
    """
    # Arrange
    facade = _make_facade(mocker)
    try:
        # Act
        before = time.monotonic()
        run_id = facade.start(_make_run_start_request())
        elapsed_s = time.monotonic() - before

        # Assert
        assert run_id == 1
        assert elapsed_s < _UNIT_DELAY_S, "start() must not block until the run finishes"
        assert facade.is_running()
        assert facade.current_run() is not None
    finally:
        facade.shutdown(int(_WAIT_TIMEOUT_S * 1000))


def test_shutdown_cancels_waits_and_joins_dispatcher_thread(mocker: MockerFixture) -> None:
    """Proves: STORY-042-AC-3

    Given a run is active on the real dispatcher thread,
    when `shutdown(timeout_ms)` is called,
    then it returns within the timeout budget and `is_running()` reports
    `False` immediately afterwards — the facade cancelled the run, waited for
    the in-flight work to settle, and joined the dispatcher thread before
    returning.
    """
    # Arrange
    facade = _make_facade(mocker)
    facade.start(_make_run_start_request())

    # Act
    before = time.monotonic()
    facade.shutdown(int(_WAIT_TIMEOUT_S * 1000))
    elapsed_s = time.monotonic() - before

    # Assert
    assert elapsed_s < _WAIT_TIMEOUT_S
    assert not facade.is_running()


_DISPATCHER_THREAD_NAME = "pipeline-dispatcher"


def test_second_run_reuses_the_same_persistent_dispatcher_thread(mocker: MockerFixture) -> None:
    """Proves: STORY-042-AC-1

    The concrete, observable proof of the DD-38 conformance fix this story
    made: given two sequential runs through the same facade, `threading.
    enumerate()` shows exactly one thread named `pipeline-dispatcher` across
    both — the dispatcher thread is created once and reused, never
    reconstructed per `start()` call.
    """
    # Arrange
    facade = _make_facade(mocker)
    try:
        # Act
        facade.start(_make_run_start_request())
        _wait_until_idle(facade)
        dispatcher_threads_after_first_run = [
            thread for thread in threading.enumerate() if thread.name == _DISPATCHER_THREAD_NAME
        ]

        facade.start(_make_run_start_request())
        _wait_until_idle(facade)
        dispatcher_threads_after_second_run = [
            thread for thread in threading.enumerate() if thread.name == _DISPATCHER_THREAD_NAME
        ]

        # Assert
        assert len(dispatcher_threads_after_first_run) == 1
        assert len(dispatcher_threads_after_second_run) == 1
        assert dispatcher_threads_after_first_run[0] is dispatcher_threads_after_second_run[0]
    finally:
        facade.shutdown(int(_WAIT_TIMEOUT_S * 1000))
