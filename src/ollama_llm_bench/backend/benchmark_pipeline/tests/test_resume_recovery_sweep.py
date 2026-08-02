"""Proves: STORY-080-AC-8"""

import time

from pytest_mock import MockerFixture

from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi, make_benchmark_pipeline
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import (
    STABILITY_SETTING_ENTRIES,
    make_task,
)
from ollama_llm_bench.backend.domain import (
    AttemptOutcome,
    BenchmarkResult,
    BenchmarkResultAttempt,
    BenchmarkResultTerm,
    BenchmarkRun,
    BenchmarkRunSettingEntry,
    ResultStatus,
    ResultTermKind,
    RunMode,
    RunStatus,
)
from ollama_llm_bench.backend.embedding.protocols import EmbeddingService
from ollama_llm_bench.backend.errors import ConfigurationError
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
_IN_FLIGHT_STATUSES = (
    ResultStatus.RUNNING_INFERENCE,
    ResultStatus.AWAITING_KEYWORD_CHECK,
    ResultStatus.AWAITING_COSINE_CHECK,
    ResultStatus.AWAITING_JUDGE_CHECK,
)


def _wait_until_idle(pipeline: BenchmarkFlowApi, timeout_s: float = _WAIT_TIMEOUT_S) -> None:
    """Poll `is_running()` until the dispatcher settles (mirrors `test_resume.py`'s helper)."""
    deadline = time.monotonic() + timeout_s
    while pipeline.is_running() and time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL_S)
    assert not pipeline.is_running(), "pipeline did not settle within the timeout"


def _make_in_flight_result(
    *, result_id: int, task_id: str, status: ResultStatus
) -> BenchmarkResult:
    """A minimal in-flight `BenchmarkResult` carrying one child term row and one child
    attempt row, so the sweep's child-row-deletion is observable for both child
    collections (mirrors `tests/integration/persistence/test_crash_recovery_sweep.py`'s
    `_make_result`)."""
    return BenchmarkResult(
        result_id=result_id,
        run_id=_RUN_ID,
        task_id=task_id,
        provider_id="11111111-1111-4111-8111-111111111111",
        provider_name="Local Ollama",
        model_name="llama3",
        status=status,
        sanitized_response="in-flight response",
        created_at="2026-01-01T00:00:00+00:00",
        terms=(
            BenchmarkResultTerm(term_kind=ResultTermKind.SEMANTIC, term_order=0, term_text="x"),
        ),
        attempts=(
            BenchmarkResultAttempt(
                attempt_index=1, timeout_ms=30_000, outcome=AttemptOutcome.TIMEOUT
            ),
        ),
    )


def _make_stopped_run() -> BenchmarkRun:
    """A minimal `STOPPED` run carrying every required settings-snapshot key
    (mirrors `test_resume.py`'s own `_make_stopped_run` — duplicated here since
    colocated test files are self-contained per `testing-standard-pyqt`)."""
    return BenchmarkRun(
        run_id=_RUN_ID,
        run_name=None,
        timestamp="2026-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=RunStatus.STOPPED,
        total_tasks=len(_IN_FLIGHT_STATUSES),
        completed_tasks=0,
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


def _make_pipeline(  # noqa: PLR0913  # every fixture is a distinct required collaborator
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


def test_resume_sweeps_in_flight_rows_before_dispatch(  # noqa: PLR0913  # every fixture is a
    # distinct required collaborator
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
    """Proves: STORY-080-AC-8

    Given result rows in each of the four non-terminal in-flight statuses, each
    carrying a child term row, when `resume(run_id)` is called, then the
    crash-recovery sweep has reset every one of the four rows to `PENDING` and
    deleted their child rows before `list_results` is read to compute the
    resumable set — replacing the old behaviour that only reset
    `RUNNING_INFERENCE` rows and never deleted any child row.
    """
    # Arrange
    rows = tuple(
        _make_in_flight_result(result_id=i + 1, task_id=f"task-{i + 1}", status=status)
        for i, status in enumerate(_IN_FLIGHT_STATUSES)
    )
    fake_results_store.create_results(rows)
    fake_runs_store.get_run.return_value = _make_stopped_run()  # type: ignore[attr-defined]
    fake_tasks_store.list_tasks.return_value = tuple(  # type: ignore[attr-defined]
        make_task(task_id=f"task-{i + 1}") for i in range(len(_IN_FLIGHT_STATUSES))
    )
    fake_provider_registry.get_client.side_effect = ConfigurationError(  # type: ignore[attr-defined]
        message="no client configured for this test"
    )

    # Capture the swept snapshot by wrapping list_results with a side effect that
    # records the return value from the first call (which occurs within resume(),
    # before the inline dispatcher runs the units).
    swept_snapshot_holder: list[tuple[BenchmarkResult, ...]] = []
    original_list_results = fake_results_store.list_results

    def capture_swept_results(run_id: int) -> tuple[BenchmarkResult, ...]:
        result = original_list_results(run_id)
        if not swept_snapshot_holder:
            swept_snapshot_holder.append(result)
        return result

    recover_spy = mocker.spy(fake_results_store, "recover_in_flight_results")
    fake_results_store.list_results = capture_swept_results  # type: ignore[method-assign]

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

    # Act
    pipeline.resume(_RUN_ID)

    # Restore original method
    fake_results_store.list_results = original_list_results  # type: ignore[method-assign]

    # Assert — the sweep ran, and by the time `list_results` was read
    # (synchronously within resume(), before the inline dispatcher runs),
    # every one of the four originally in-flight rows was already PENDING with
    # its child rows cleared.
    recover_spy.assert_called_once()
    assert swept_snapshot_holder, "list_results was never called during resume"
    swept_snapshot = swept_snapshot_holder[0]
    assert {row.result_id: row.status for row in swept_snapshot} == dict.fromkeys(
        range(1, len(_IN_FLIGHT_STATUSES) + 1), ResultStatus.PENDING
    )
    assert all(row.terms == () for row in swept_snapshot)
    assert all(row.attempts == () for row in swept_snapshot)
