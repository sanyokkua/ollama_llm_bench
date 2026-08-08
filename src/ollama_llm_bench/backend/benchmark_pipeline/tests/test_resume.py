"""Proves: STORY-029-AC-6"""

from collections.abc import Iterator
import time

from pytest_mock import MockerFixture

from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi, make_benchmark_pipeline
from ollama_llm_bench.backend.benchmark_pipeline.testing import make_benchmark_result
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import (
    STABILITY_SETTING_ENTRIES,
    StagesNoTasks,
    make_task,
)
from ollama_llm_bench.backend.domain.models import (
    BenchmarkRun,
    BenchmarkRunSettingEntry,
    ChatChunk,
    ChatResponse,
    ResultStatus,
    RunMode,
    RunStatus,
)
from ollama_llm_bench.backend.embedding.protocols import EmbeddingService
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.persistence.tasks.protocols import TasksStore
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry
from ollama_llm_bench.backend.settings.protocols import RunSnapshotBuilder, SettingsService
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore

_RUN_ID = 1
_WAIT_TIMEOUT_S = 2.0
_POLL_INTERVAL_S = 0.01


class _FakeChatStream:
    """A minimal `ChatStream` double yielding one canned chunk, then a response.

    Mirrors `test_pause_stop.py`'s own copy of the same shape — the resumed
    run's dispatcher thread runs for real (a genuine `threading.Thread`), so
    its inference unit needs a real iterable stream rather than a bare
    `mocker.Mock()`, which is not iterable and would surface as an unhandled
    `TypeError` on the dispatcher thread instead of exercising this test's
    resume-specific assertions.
    """

    def __init__(self, *, chunks: tuple[ChatChunk, ...], response: ChatResponse) -> None:
        self._chunks = chunks
        self._response = response

    def __iter__(self) -> Iterator[ChatChunk]:
        return iter(self._chunks)

    def __next__(self) -> ChatChunk:  # pragma: no cover — iteration goes via __iter__
        raise StopIteration

    def trailing_response(self) -> ChatResponse:
        return self._response


def _wait_until_idle(pipeline: BenchmarkFlowApi, timeout_s: float = _WAIT_TIMEOUT_S) -> None:
    """Poll `is_running()` from the test's own thread until the dispatcher settles.

    Mirrors `test_pause_stop.py`'s helper: `resume()` genuinely spawns the
    `pipeline-dispatcher` thread, so a test must wait for it to finish before
    returning — otherwise a leftover background thread can still be mutating
    shared fakes (or raising) after the test function itself has completed.
    """
    deadline = time.monotonic() + timeout_s
    while pipeline.is_running() and time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL_S)
    assert not pipeline.is_running(), "pipeline did not settle within the timeout"


def _make_stopped_run() -> BenchmarkRun:
    """A minimal, previously-`STOPPED` run carrying a frozen settings snapshot.

    Carries every `eval.*` key `make_sanity_checker`'s own contract requires
    (`REQUIRED_EVALUATION_SETTING_KEYS`) plus every `AdaptiveTimeoutService`/
    `ProviderCircuitBreaker` required key (`STABILITY_SETTING_ENTRIES`,
    STORY-030), since `resume()` genuinely spawns the `pipeline-dispatcher`
    thread, which constructs this run's evaluators and stability services
    from `run.settings_snapshot` exactly as `start()` would.
    """
    return BenchmarkRun(
        run_id=_RUN_ID,
        run_name=None,
        timestamp="2026-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=RunStatus.STOPPED,
        total_tasks=2,
        completed_tasks=1,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2026-01-01T00:00:00+00:00",
        settings_snapshot=(
            BenchmarkRunSettingEntry(setting_key="eval.sanity_min_chars", setting_value="1"),
            BenchmarkRunSettingEntry(setting_key="eval.sanity_error_markers", setting_value=""),
            BenchmarkRunSettingEntry(
                setting_key="eval.keyword_semantic_pass_threshold", setting_value="0.8"
            ),
            BenchmarkRunSettingEntry(
                setting_key="eval.judge_max_completion_tokens", setting_value="512"
            ),
            BenchmarkRunSettingEntry(setting_key="eval.judge_max_parse_retries", setting_value="2"),
            BenchmarkRunSettingEntry(
                setting_key="eval.force_judge_on_prior_failure", setting_value="false"
            ),
            *STABILITY_SETTING_ENTRIES,
        ),
    )


def _make_pipeline(  # noqa: PLR0913  # test wiring must name every fixture collaborator
    *,
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    inline_run_dispatcher: object,
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
        task_stager=StagesNoTasks(),
        inference_activity_store=fake_inference_activity_store,
        task_runner=inline_task_runner,  # type: ignore[arg-type]  # fixture is TaskRunner[ResultPatch]
        run_dispatcher=inline_run_dispatcher,  # type: ignore[arg-type]  # fixture is RunDispatcher
        bus=fake_event_bus,  # type: ignore[arg-type]  # fixture satisfies EventBus structurally
        clock=fake_clock,
        embedding_service=fake_embedding_service,
        provider_registry=fake_provider_registry,
        settings_service=fake_settings_service,
        run_snapshot_builder=fake_run_snapshot_builder,
    )


def test_resume_selects_resumable_rows_and_reuses_snapshot(  # noqa: PLR0913  # every
    # fixture is a distinct collaborator the composition-level factory call requires
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    inline_run_dispatcher: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-029-AC-6

    A `RUNNING_INFERENCE` row resets to `PENDING` before resume dispatches,
    then is picked back up and driven to completion by the same dispatcher
    loop `start()` uses; a `COMPLETED` row is left untouched throughout; the
    run's frozen `settings_snapshot` is re-read from `RunsStore.get_run`
    rather than re-resolved from live settings (`RunSnapshotBuilder
    .build_snapshot` is never called by `resume()`).
    """
    stuck_row = make_benchmark_result(
        result_id=1, run_id=_RUN_ID, task_id="task-1", status=ResultStatus.RUNNING_INFERENCE
    )
    done_row = make_benchmark_result(
        result_id=2, run_id=_RUN_ID, task_id="task-2", status=ResultStatus.COMPLETED
    )
    fake_results_store.create_results((stuck_row, done_row))
    stopped_run = _make_stopped_run()
    fake_runs_store.get_run.return_value = stopped_run  # type: ignore[attr-defined]
    fake_tasks_store.list_tasks.return_value = (  # type: ignore[attr-defined]
        make_task(task_id="task-1"),
        make_task(task_id="task-2"),
    )
    client = mocker.Mock()
    client.chat_stream.return_value = _FakeChatStream(
        chunks=(ChatChunk(content="Paris.", delta_tokens=3),),
        response=ChatResponse(
            text="Paris.", total_time_ms=10, ttft_ms=5, prompt_tokens=5, completion_tokens=3
        ),
    )
    fake_provider_registry.get_client.return_value = client  # type: ignore[attr-defined]

    pipeline = _make_pipeline(
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_tasks_store=fake_tasks_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        inline_run_dispatcher=inline_run_dispatcher,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )

    pipeline.resume(_RUN_ID)
    _wait_until_idle(pipeline)

    rows_by_id = {row.result_id: row for row in fake_results_store.list_results(_RUN_ID)}
    assert rows_by_id[1].status is ResultStatus.COMPLETED
    assert rows_by_id[2].status is ResultStatus.COMPLETED
    fake_runs_store.get_run.assert_called_once_with(_RUN_ID)  # type: ignore[attr-defined]
    fake_run_snapshot_builder.build_snapshot.assert_not_called()  # type: ignore[attr-defined]
    assert "_run_resumed" in fake_event_bus.emitted_signal_names()  # type: ignore[attr-defined]


def test_resume_with_gate_already_held_is_a_no_op(  # noqa: PLR0913  # every fixture is a
    # distinct collaborator the composition-level factory call requires
    fake_results_store: FakeResultsStore,
    fake_runs_store: RunsStore,
    fake_tasks_store: TasksStore,
    fake_inference_activity_store: InferenceActivityStore,
    inline_task_runner: object,
    inline_run_dispatcher: object,
    fake_event_bus: object,
    fake_clock: Clock,
    fake_embedding_service: EmbeddingService,
    fake_provider_registry: ProviderRegistry,
    fake_settings_service: SettingsService,
    fake_run_snapshot_builder: RunSnapshotBuilder,
) -> None:
    """Proves: STORY-029-AC-6

    Gate admission is `resume`'s first synchronous step, exactly like
    `start`: a failed `try_acquire` leaves every row untouched and re-reads
    nothing from `RunsStore`.
    """
    fake_inference_activity_store.try_acquire.return_value = None  # type: ignore[attr-defined]
    stuck_row = make_benchmark_result(
        result_id=1, run_id=_RUN_ID, task_id="task-1", status=ResultStatus.RUNNING_INFERENCE
    )
    fake_results_store.create_results((stuck_row,))

    pipeline = _make_pipeline(
        fake_results_store=fake_results_store,
        fake_runs_store=fake_runs_store,
        fake_tasks_store=fake_tasks_store,
        fake_inference_activity_store=fake_inference_activity_store,
        inline_task_runner=inline_task_runner,
        inline_run_dispatcher=inline_run_dispatcher,
        fake_event_bus=fake_event_bus,
        fake_clock=fake_clock,
        fake_embedding_service=fake_embedding_service,
        fake_provider_registry=fake_provider_registry,
        fake_settings_service=fake_settings_service,
        fake_run_snapshot_builder=fake_run_snapshot_builder,
    )

    pipeline.resume(_RUN_ID)

    rows_by_id = {row.result_id: row for row in fake_results_store.list_results(_RUN_ID)}
    assert rows_by_id[1].status is ResultStatus.RUNNING_INFERENCE
    fake_runs_store.get_run.assert_not_called()  # type: ignore[attr-defined]
    assert not pipeline.is_running()
