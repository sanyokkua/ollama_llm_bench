"""Proves: STORY-030-AC-3, STORY-030-AC-4

Per-task judge-timeout-ladder exhaustion settles `FAILED_JUDGE_TIMEOUT` and the
run continues; crossing `eval.judge_timeout_consecutive_threshold` consecutive
max-budget judge timeouts excludes the judge model run-wide, emitting
`_judge_model_excluded` exactly once and skipping the judge call for every
remaining judge-eligible task while Phase 2/3 work continues normally.

Also proves the STORY-030 Task 1 fix: `JudgeStartedEvent` carries the run's
resolved judge target, never the row's own test-model identity.
"""

from collections.abc import Callable
from concurrent.futures import Future

from ollama_llm_bench.backend.adaptive_timeout import make_adaptive_timeout_service
from ollama_llm_bench.backend.adaptive_timeout.protocols import AdaptiveTimeoutService
from ollama_llm_bench.backend.benchmark_pipeline._internal.stability_phase import (
    StabilityCollaborators,
    StabilityRunState,
    run_stability_phase,
)
from ollama_llm_bench.backend.benchmark_pipeline.models import Phase
from ollama_llm_bench.backend.benchmark_pipeline.testing import make_benchmark_result
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import (
    FakeClock,
    make_cancellation_token,
    make_task,
)
from ollama_llm_bench.backend.circuit_breaker import make_circuit_breaker
from ollama_llm_bench.backend.circuit_breaker.protocols import ProviderCircuitBreaker
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkRunModelEntry,
    BenchmarkRunSettingEntry,
    BenchmarkTask,
    ErrorKind,
    ModelRole,
    ResultId,
    ResultPatch,
    ResultStatus,
    RunMode,
    RunStatus,
)
from ollama_llm_bench.backend.errors import ErrorContext, HttpTimeoutError
from ollama_llm_bench.backend.evaluation.models import JudgePhaseResult
from ollama_llm_bench.backend.evaluation.protocols import JudgeEvaluator
from ollama_llm_bench.backend.events.models import (
    SIGNAL_JUDGE_MODEL_EXCLUDED,
    JudgeModelExcludedEvent,
    JudgeStartedEvent,
)

_TEST_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_TEST_MODEL_NAME = "llama3"
_JUDGE_PROVIDER_ID = "22222222-2222-4222-8222-222222222222"
_JUDGE_MODEL_NAME = "judge-model"
_CONSECUTIVE_THRESHOLD = 2
_TASK_COUNT_BEYOND_THRESHOLD = 4

_JUDGE_STABILITY_SETTINGS: tuple[BenchmarkRunSettingEntry, ...] = (
    # A degenerate, deterministic ladder: every attempt is immediately "at max",
    # so `record_timeout` increments the exclusion counter on every judge timeout.
    BenchmarkRunSettingEntry(setting_key="eval.judge_timeout_min_seconds", setting_value="1"),
    BenchmarkRunSettingEntry(setting_key="eval.judge_timeout_max_seconds", setting_value="1"),
    BenchmarkRunSettingEntry(setting_key="eval.judge_timeout_escalation_steps", setting_value="0"),
    BenchmarkRunSettingEntry(
        setting_key="eval.judge_timeout_consecutive_threshold",
        setting_value=str(_CONSECUTIVE_THRESHOLD),
    ),
    BenchmarkRunSettingEntry(setting_key="benchmark.min_timeout_seconds", setting_value="1"),
    BenchmarkRunSettingEntry(setting_key="benchmark.max_timeout_seconds", setting_value="1"),
    BenchmarkRunSettingEntry(setting_key="benchmark.retry_count", setting_value="0"),
    BenchmarkRunSettingEntry(
        setting_key="benchmark.consecutive_max_timeouts_to_exclude", setting_value="3"
    ),
    BenchmarkRunSettingEntry(setting_key="circuit_breaker.enabled", setting_value="true"),
    BenchmarkRunSettingEntry(setting_key="circuit_breaker.failure_threshold", setting_value="5"),
    BenchmarkRunSettingEntry(setting_key="circuit_breaker.cooldown_seconds", setting_value="30"),
)


class _InlineTaskRunner:
    """Runs a unit synchronously on the calling thread — a test double only."""

    def submit(self, fn: Callable[[], object], *, token: CancellationToken) -> "Future[object]":
        del token
        future: Future[object] = Future()
        try:
            future.set_result(fn())
        except BaseException as exc:  # noqa: BLE001  # captured for the Future, not swallowed
            future.set_exception(exc)
        return future


class _RecordingBus:
    """A minimal `EventBus` double recording every emitted `(signal, payload)`."""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> None:
        del signal_name, handler, owner

    def emit(self, signal_name: str, payload: object) -> None:
        self.emitted.append((signal_name, payload))


class _AlwaysTimesOutJudgeEvaluator:
    """A `JudgeEvaluator` double that raises `HttpTimeoutError` on every call and
    counts its invocations."""

    def __init__(self) -> None:
        self.call_count = 0

    def evaluate(
        self,
        *,
        response: str,
        system_prompt_sent: str | None,
        task: BenchmarkTask,
        timeout_ms: int,
        token: CancellationToken,
    ) -> JudgePhaseResult:
        del response, system_prompt_sent, task, timeout_ms, token
        self.call_count += 1
        raise HttpTimeoutError(message="judge call timed out", context=ErrorContext())


def _make_run() -> BenchmarkRun:
    return BenchmarkRun(
        run_id=1,
        run_name=None,
        timestamp="2026-01-01T00:00:00+00:00",
        run_mode=RunMode.GRADED,
        status=RunStatus.INCOMPLETE,
        total_tasks=1,
        completed_tasks=0,
        total_elapsed_ms=0,
        judge_provider_id=_JUDGE_PROVIDER_ID,
        judge_provider_name="Judge Provider",
        schema_version=1,
        created_at="2026-01-01T00:00:00+00:00",
        models=(
            BenchmarkRunModelEntry(
                role=ModelRole.TEST, provider_id=_TEST_PROVIDER_ID, model_name=_TEST_MODEL_NAME
            ),
            BenchmarkRunModelEntry(
                role=ModelRole.JUDGE, provider_id=_JUDGE_PROVIDER_ID, model_name=_JUDGE_MODEL_NAME
            ),
        ),
        settings_snapshot=_JUDGE_STABILITY_SETTINGS,
    )


def _make_row(result_id: ResultId, task_id: str) -> BenchmarkResult:
    return make_benchmark_result(
        result_id=result_id,
        task_id=task_id,
        provider_id=_TEST_PROVIDER_ID,
        model_name=_TEST_MODEL_NAME,
        status=ResultStatus.AWAITING_JUDGE_CHECK,
    )


class _FakeSettingsService:
    """A minimal `SettingsService` double reading only from `run.settings_snapshot`."""

    def __init__(self, run: BenchmarkRun) -> None:
        self._values = {entry.setting_key: entry.setting_value for entry in run.settings_snapshot}

    def get_int(self, key: str, run: BenchmarkRun | None = None) -> int:
        del run
        return int(self._values[key])

    def get_bool(self, key: str, run: BenchmarkRun | None = None) -> bool:
        del run
        return self._values[key].strip().lower() == "true"


def _make_services(run: BenchmarkRun) -> tuple[AdaptiveTimeoutService, ProviderCircuitBreaker]:
    """Build this test's `(AdaptiveTimeoutService, ProviderCircuitBreaker)` pair."""
    adaptive_timeout = make_adaptive_timeout_service(snapshot=run.settings_snapshot)
    circuit_breaker = make_circuit_breaker(snapshot=run.settings_snapshot, clock=FakeClock())
    return adaptive_timeout, circuit_breaker


def _run_judge_check_phase(
    *,
    run: BenchmarkRun,
    rows: tuple[BenchmarkResult, ...],
    judge_evaluator: JudgeEvaluator,
    bus: _RecordingBus,
    services: tuple[AdaptiveTimeoutService, ProviderCircuitBreaker],
) -> dict[ResultId, ResultPatch]:
    """Drive one JUDGE_CHECK phase over `rows`, returning each row's persisted patch."""
    patches: dict[ResultId, ResultPatch] = {}
    adaptive_timeout, circuit_breaker = services

    class _RecordingResultsStore:
        def update_result(self, result_id: ResultId, patch: ResultPatch) -> None:
            patches[result_id] = patch

    tasks_by_id = {row.task_id: make_task(task_id=row.task_id) for row in rows}
    groups = ((_TEST_PROVIDER_ID, _TEST_MODEL_NAME, rows),)
    run_stability_phase(
        phase=Phase.JUDGE_CHECK,
        groups=groups,
        run=run,
        tasks_by_id=tasks_by_id,
        sanity_checker=None,  # type: ignore[arg-type]  # unused by role=JUDGE
        judge_evaluator=judge_evaluator,
        token=make_cancellation_token(),
        keyword_enabled=True,
        cosine_enabled=True,
        judge_enabled=True,
        force_judge_on_prior_failure=False,
        collaborators=StabilityCollaborators(
            bus=bus,  # type: ignore[arg-type]  # structurally satisfies EventBus
            clock=FakeClock(),
            provider_registry=None,  # type: ignore[arg-type]  # unused by role=JUDGE
            results_store=_RecordingResultsStore(),  # type: ignore[arg-type]
            settings_service=_FakeSettingsService(run),  # type: ignore[arg-type]
            task_runner=_InlineTaskRunner(),
        ),
        state=StabilityRunState(),
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=circuit_breaker,
        retry_count=0,
        warmup_enabled=False,
    )
    return patches


def test_per_task_judge_timeout_settles_failed_judge_timeout() -> None:
    """Proves: STORY-030-AC-3

    A judge call whose fake evaluator times out on every attempt settles the
    row to FAILED_JUDGE_TIMEOUT with error_kind=JUDGE_TIMEOUT and verdict=None
    — not the generic FAILED_TIMEOUT a naive reuse of contain_unit_failure
    would produce — and the pipeline proceeds (no exception propagates).
    """
    run = _make_run()
    row = _make_row(result_id=1, task_id="task-1")
    evaluator = _AlwaysTimesOutJudgeEvaluator()
    bus = _RecordingBus()

    patches = _run_judge_check_phase(
        run=run, rows=(row,), judge_evaluator=evaluator, bus=bus, services=_make_services(run)
    )

    patch = patches[1]
    assert patch.status is ResultStatus.FAILED_JUDGE_TIMEOUT
    assert patch.error_kind is ErrorKind.JUDGE_TIMEOUT
    assert patch.verdict is None
    assert patch.resolution_layer is None


def test_judge_started_event_carries_run_judge_target_not_row_test_model() -> None:
    """Proves: STORY-030 (Task 1 judge-target fix)

    `JudgeStartedEvent.judge_provider_id`/`judge_model_name` equal the run's
    judge model, not the row's own `provider_id`/`model_name` — even though
    this row's own test model differs from the judge model.
    """
    run = _make_run()
    row = _make_row(result_id=1, task_id="task-1")
    evaluator = _AlwaysTimesOutJudgeEvaluator()
    bus = _RecordingBus()

    _run_judge_check_phase(
        run=run, rows=(row,), judge_evaluator=evaluator, bus=bus, services=_make_services(run)
    )

    started_events = [payload for signal, payload in bus.emitted if signal == "_judge_started"]
    assert len(started_events) == 1
    started = started_events[0]
    assert isinstance(started, JudgeStartedEvent)
    assert started.judge_provider_id == _JUDGE_PROVIDER_ID
    assert started.judge_model_name == _JUDGE_MODEL_NAME
    assert started.judge_provider_id != row.provider_id
    assert started.judge_model_name != row.model_name


def test_run_wide_judge_exclusion_skips_remaining_and_continues() -> None:
    """Proves: STORY-030-AC-4

    Across N tasks (N > eval.judge_timeout_consecutive_threshold) all hitting
    judge timeouts, exactly one _judge_model_excluded event is emitted; every
    task after the threshold-crossing task settles FAILED_JUDGE_TIMEOUT with
    the fake JudgeEvaluator's call count not incrementing for those tasks (no
    judge call attempted); each such task's pre-seeded keyword/cosine outputs
    are still populated — proving Phase 2/3 already ran; the phase call itself
    never raises (the run does not abort).
    """
    run = _make_run()
    rows = tuple(
        make_benchmark_result(
            result_id=index + 1,
            task_id=f"task-{index + 1}",
            provider_id=_TEST_PROVIDER_ID,
            model_name=_TEST_MODEL_NAME,
            status=ResultStatus.AWAITING_JUDGE_CHECK,
        )
        for index in range(_TASK_COUNT_BEYOND_THRESHOLD)
    )
    evaluator = _AlwaysTimesOutJudgeEvaluator()
    bus = _RecordingBus()

    patches = _run_judge_check_phase(
        run=run, rows=rows, judge_evaluator=evaluator, bus=bus, services=_make_services(run)
    )

    excluded_events = [
        payload for signal, payload in bus.emitted if signal == SIGNAL_JUDGE_MODEL_EXCLUDED
    ]
    assert len(excluded_events) == 1
    excluded_payload = excluded_events[0]
    assert isinstance(excluded_payload, JudgeModelExcludedEvent)
    assert excluded_payload.provider_id == _JUDGE_PROVIDER_ID
    assert excluded_payload.model_name == _JUDGE_MODEL_NAME

    for row in rows:
        assert patches[row.result_id].status is ResultStatus.FAILED_JUDGE_TIMEOUT

    # Exactly `_CONSECUTIVE_THRESHOLD` tasks actually invoked the judge evaluator
    # before exclusion kicked in; every task after that used the pre-attempt
    # fast path (no judge call attempted).
    assert evaluator.call_count == _CONSECUTIVE_THRESHOLD
