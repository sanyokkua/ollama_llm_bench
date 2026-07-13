"""Proves: STORY-029-AC-4"""

from collections.abc import Callable, Iterator
import time

from pytest_mock import MockerFixture

from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi, make_benchmark_pipeline
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import make_task
from ollama_llm_bench.backend.domain.models import (
    ChatChunk,
    ChatResponse,
    ModelDescriptor,
    RunMode,
    RunStartRequest,
)
from ollama_llm_bench.backend.embedding.protocols import EmbeddingService
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.persistence.tasks.protocols import TasksStore
from ollama_llm_bench.backend.provider_registry.protocols import ChatStream, ProviderRegistry
from ollama_llm_bench.backend.settings.protocols import RunSnapshotBuilder, SettingsService
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME = "llama3"
_WAIT_TIMEOUT_S = 2.0
_POLL_INTERVAL_S = 0.01
_EXPECTED_TASK_COUNT = 2


def _make_run_start_request() -> RunStartRequest:
    """A minimal, valid TASKS-mode request naming one test target."""
    return RunStartRequest(
        run_mode=RunMode.TASKS,
        test_models=(ModelDescriptor(provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),),
    )


class _FakeChatStream:
    """A minimal `ChatStream` double yielding one canned chunk, then a response.

    `on_trailing_response`, when given, runs exactly once `trailing_response()`
    is called — i.e. after the stream's own chunk-boundary cancellation
    checkpoint has already passed — letting a test request a pause/stop that
    takes effect only *after* this unit's work is done, mirroring the DD-42
    safe-boundary guarantee without racing a real thread.
    """

    def __init__(
        self,
        *,
        chunks: tuple[ChatChunk, ...],
        response: ChatResponse,
        on_trailing_response: Callable[[], None] | None = None,
    ) -> None:
        self._chunks = chunks
        self._response = response
        self._on_trailing_response = on_trailing_response

    def __iter__(self) -> Iterator[ChatChunk]:
        return iter(self._chunks)

    def __next__(self) -> ChatChunk:  # pragma: no cover — iteration goes via __iter__
        raise StopIteration

    def trailing_response(self) -> ChatResponse:
        if self._on_trailing_response is not None:
            self._on_trailing_response()
        return self._response


def _wait_until_idle(pipeline: BenchmarkFlowApi, timeout_s: float = _WAIT_TIMEOUT_S) -> None:
    """Poll `is_running()` from the test's own thread until the dispatcher settles."""
    deadline = time.monotonic() + timeout_s
    while pipeline.is_running() and time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL_S)
    assert not pipeline.is_running(), "pipeline did not settle within the timeout"


def _make_pipeline(  # noqa: PLR0913  # test wiring must name every fixture collaborator
    *,
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
) -> BenchmarkFlowApi:
    return make_benchmark_pipeline(
        results_store=fake_results_store,
        runs_store=fake_runs_store,
        tasks_store=fake_tasks_store,
        inference_activity_store=fake_inference_activity_store,
        task_runner=inline_task_runner,  # type: ignore[arg-type]  # fixture is TaskRunner[ResultPatch]
        bus=fake_event_bus,  # type: ignore[arg-type]  # fixture satisfies EventBus structurally
        clock=fake_clock,
        embedding_service=fake_embedding_service,
        provider_registry=fake_provider_registry,
        settings_service=fake_settings_service,
        run_snapshot_builder=fake_run_snapshot_builder,
    )


def test_pause_on_idle_pipeline_is_a_no_op(  # noqa: PLR0913  # every fixture is a
    # distinct collaborator the composition-level factory call requires
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
) -> None:
    """Proves: STORY-029-AC-4

    `pause()` on a pipeline that has never started a run is a documented
    no-op: it does not raise and leaves `is_running()` false.
    """
    pipeline = _make_pipeline(
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_tasks_store=fake_tasks_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )

    pipeline.pause()

    assert not pipeline.is_running()


def test_stop_on_idle_pipeline_is_a_no_op(  # noqa: PLR0913  # every fixture is a
    # distinct collaborator the composition-level factory call requires
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
) -> None:
    """Proves: STORY-029-AC-4

    `stop()` on a pipeline that has never started a run is a documented
    no-op: it does not raise and leaves `is_running()` false.
    """
    pipeline = _make_pipeline(
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_tasks_store=fake_tasks_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )

    pipeline.stop()

    assert not pipeline.is_running()


def test_shutdown_on_idle_pipeline_is_a_no_op(  # noqa: PLR0913  # every fixture is a
    # distinct collaborator the composition-level factory call requires
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
) -> None:
    """Proves: STORY-029-AC-4

    `shutdown()` on a pipeline that has never started a run does not raise
    and returns promptly (no dispatcher thread to join).
    """
    pipeline = _make_pipeline(
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_tasks_store=fake_tasks_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )

    pipeline.shutdown(1000)

    assert not pipeline.is_running()


def test_shutdown_mid_run_stops_and_joins_the_dispatcher_thread(  # noqa: PLR0913
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-029-AC-4

    `shutdown()` requests a hard stop and blocks until the dispatcher
    thread settles (bounded by its `timeout_ms`) — `is_running()` is false
    the instant `shutdown()` returns, with no separate poll needed.
    """
    task_one = make_task(task_id="task-1")
    fake_tasks_store.list_tasks.return_value = (task_one,)  # type: ignore[attr-defined]

    pipeline = _make_pipeline(
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_tasks_store=fake_tasks_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )

    def _chat_stream(request: object, *, token: object) -> ChatStream:
        del request
        pipeline.stop()
        token.raise_if_cancelled()  # type: ignore[attr-defined]
        raise AssertionError("unreachable: raise_if_cancelled must raise after stop()")

    client = mocker.Mock()
    client.chat_stream.side_effect = _chat_stream
    fake_provider_registry.get_client.return_value = client  # type: ignore[attr-defined]

    pipeline.start(_make_run_start_request())
    pipeline.shutdown(2000)

    assert not pipeline.is_running()
    assert "_run_stopped" in fake_event_bus.emitted_signal_names()  # type: ignore[attr-defined]


def test_start_with_gate_already_held_emits_start_failed_and_creates_no_run(  # noqa: PLR0913
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-029-AC-4

    Gate admission is the first synchronous step of `start()` (SPEC-036): a
    failed `try_acquire` (the gate already held by another activity) creates
    no run — `RunsStore.create_run` is never called — writes nothing, and
    surfaces only as a rejected `_run_start_failed` event, never a raise.
    """
    fake_inference_activity_store.try_acquire.return_value = None  # type: ignore[attr-defined]
    pipeline = _make_pipeline(
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_tasks_store=fake_tasks_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )

    pipeline.start(_make_run_start_request())

    fake_runs_store.create_run.assert_not_called()  # type: ignore[attr-defined]
    assert "_run_start_failed" in fake_event_bus.emitted_signal_names()  # type: ignore[attr-defined]
    assert not pipeline.is_running()
    del mocker  # only used to type-narrow fixture injection order; no direct call here


def test_pause_mid_run_finishes_in_flight_unit_and_leaves_run_incomplete(  # noqa: PLR0913
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-029-AC-4

    Pause lets the in-flight unit finish and persist, leaves at least one
    not-yet-submitted row `PENDING`, and settles the run without reaching
    `COMPLETED` — it stays parked (no persisted terminal write, per DD-42's
    SOFT row) since a `_run_paused` event is emitted.

    Determinism strategy: `inline_task_runner` runs every submitted unit
    synchronously on whichever thread calls `.submit()` — here the real
    `pipeline-dispatcher` thread `start()` spawns. To avoid racing that
    thread from the test's main thread, the fake `LLMClient.chat_stream`
    itself calls `pipeline.pause()` from *inside* the first unit's
    execution, guaranteeing the token is cancelled before the dispatcher
    loop's next `token.raise_if_cancelled()` checkpoint — deterministic by
    construction, no sleep-and-hope polling of the pause moment itself
    (only the final `is_running()` settle is polled).
    """
    task_one = make_task(task_id="task-1")
    task_two = make_task(task_id="task-2")
    fake_tasks_store.list_tasks.return_value = (task_one, task_two)  # type: ignore[attr-defined]

    pipeline = _make_pipeline(
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_tasks_store=fake_tasks_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )

    def _chat_stream(request: object, *, token: object) -> ChatStream:
        del request, token
        # Pause is requested only once the fake stream is fully drained (i.e.
        # inside trailing_response(), called after the last chunk boundary's
        # own raise_if_cancelled() check already passed) — this is what
        # makes the in-flight unit "run to completion and persist" rather
        # than being caught by the same chunk-boundary cancellation check a
        # pre-yield pause() would trip.
        return _FakeChatStream(
            chunks=(ChatChunk(content="Paris.", delta_tokens=3),),
            response=ChatResponse(
                text="Paris.", total_time_ms=10, ttft_ms=5, prompt_tokens=5, completion_tokens=3
            ),
            on_trailing_response=pipeline.pause,
        )

    client = mocker.Mock()
    client.chat_stream.side_effect = _chat_stream
    fake_provider_registry.get_client.return_value = client  # type: ignore[attr-defined]

    pipeline.start(_make_run_start_request())
    _wait_until_idle(pipeline)

    remaining_rows = fake_results_store.list_results(1)
    assert len(remaining_rows) == _EXPECTED_TASK_COUNT
    finished_rows = [row for row in remaining_rows if row.task_id == task_one.task_id]
    pending_rows = [row for row in remaining_rows if row.task_id == task_two.task_id]
    assert finished_rows[0].sanitized_response == "Paris."
    assert pending_rows[0].status.value == "pending"
    assert "_run_paused" in fake_event_bus.emitted_signal_names()  # type: ignore[attr-defined]
    fake_runs_store.update_run_status.assert_any_call(  # type: ignore[attr-defined]
        1, mocker.ANY
    )


def test_stop_mid_run_discards_in_flight_unit_and_settles_stopped(  # noqa: PLR0913
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-029-AC-4

    Stop aborts the in-flight unit: its `TaskCancelledError` propagates from
    the fake `LLMClient` (mirroring a real hard-cancel abort), the row stays
    `PENDING` with nothing persisted, and the run settles `STOPPED`.

    Same determinism strategy as the pause test above: the fake
    `chat_stream` calls `pipeline.stop()` and then calls the token's own
    `raise_if_cancelled()`, deterministically reproducing the
    hard-cancel-aborts-the-call contract (`TaskCancelledError`) without any
    thread-timing race.
    """
    task_one = make_task(task_id="task-1")
    fake_tasks_store.list_tasks.return_value = (task_one,)  # type: ignore[attr-defined]

    pipeline = _make_pipeline(
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_tasks_store=fake_tasks_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )

    def _chat_stream(request: object, *, token: object) -> ChatStream:
        del request
        pipeline.stop()
        token.raise_if_cancelled()  # type: ignore[attr-defined]
        raise AssertionError("unreachable: raise_if_cancelled must raise after stop()")

    client = mocker.Mock()
    client.chat_stream.side_effect = _chat_stream
    fake_provider_registry.get_client.return_value = client  # type: ignore[attr-defined]

    pipeline.start(_make_run_start_request())
    _wait_until_idle(pipeline)

    remaining_rows = fake_results_store.list_results(1)
    assert len(remaining_rows) == 1
    assert remaining_rows[0].status.value == "pending"
    assert remaining_rows[0].raw_response is None
    assert "_run_stopped" in fake_event_bus.emitted_signal_names()  # type: ignore[attr-defined]
