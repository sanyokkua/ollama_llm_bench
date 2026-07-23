"""Proves: STORY-030-AC-5

A row's re-entry into `run_all_phases` is determined by its reset status
(DD-66 stage-preserving retry): `PENDING` re-runs the whole task end-to-end;
`AWAITING_JUDGE_CHECK` runs only the judge against the preserved
`sanitized_response`, recomputing nothing upstream; `FAILED_JUDGE_TIMEOUT`
retried (reset to `PENDING`, DD-34) re-runs the whole task end-to-end, same as
any other `PENDING` row.

This is the already-existing `eligible_for_phase`/`run_all_phases` routing
mechanism (STORY-029) — no new production routing code is needed for this
story; this file proves that mechanism handles every row of AC-5's table.
"""

from collections.abc import Callable
from concurrent.futures import Future
from typing import TYPE_CHECKING

import msgspec
import pytest

from ollama_llm_bench.backend.adaptive_timeout import make_adaptive_timeout_service
from ollama_llm_bench.backend.benchmark_pipeline._internal.dispatcher import run_all_phases
from ollama_llm_bench.backend.benchmark_pipeline._internal.stability_phase import (
    StabilityCollaborators,
    StabilityRunState,
    run_stability_phase,
)
from ollama_llm_bench.backend.benchmark_pipeline._internal.units import (
    build_cosine_unit,
    build_keyword_unit,
)
from ollama_llm_bench.backend.benchmark_pipeline.models import Phase
from ollama_llm_bench.backend.benchmark_pipeline.testing import make_benchmark_result
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import (
    FakeClock,
    make_cancellation_token,
    make_task,
)
from ollama_llm_bench.backend.circuit_breaker import make_circuit_breaker
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkRunModelEntry,
    BenchmarkRunSettingEntry,
    BenchmarkTask,
    ChatChunk,
    ChatRequest,
    ChatResponse,
    ModelRole,
    ResultId,
    ResultPatch,
    ResultStatus,
    RunMode,
    RunStatus,
    Verdict,
)
from ollama_llm_bench.backend.evaluation.models import (
    CosinePhaseResult,
    JudgePhaseOutcome,
    JudgePhaseResult,
    KeywordPhaseResult,
)
from ollama_llm_bench.backend.provider_registry.protocols import ChatStream, LLMClient

if TYPE_CHECKING:
    from ollama_llm_bench.backend.adaptive_timeout.protocols import AdaptiveTimeoutService
    from ollama_llm_bench.backend.circuit_breaker.protocols import ProviderCircuitBreaker

_TEST_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_TEST_MODEL_NAME = "llama3"
_JUDGE_PROVIDER_ID = "22222222-2222-4222-8222-222222222222"
_JUDGE_MODEL_NAME = "judge-model"
_SEEDED_SANITIZED_RESPONSE = "The capital of France is Paris."
_SEEDED_COSINE_SIMILARITY = 0.93

_STABILITY_SETTINGS: tuple[BenchmarkRunSettingEntry, ...] = (
    BenchmarkRunSettingEntry(setting_key="eval.judge_timeout_min_seconds", setting_value="20"),
    BenchmarkRunSettingEntry(setting_key="eval.judge_timeout_max_seconds", setting_value="120"),
    BenchmarkRunSettingEntry(setting_key="eval.judge_timeout_escalation_steps", setting_value="2"),
    BenchmarkRunSettingEntry(
        setting_key="eval.judge_timeout_consecutive_threshold", setting_value="3"
    ),
    BenchmarkRunSettingEntry(setting_key="benchmark.min_timeout_seconds", setting_value="5"),
    BenchmarkRunSettingEntry(setting_key="benchmark.max_timeout_seconds", setting_value="30"),
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
    """A minimal no-op `EventBus` double — this test asserts on evaluator call
    counts and persisted rows, not on emitted events."""

    def subscribe(
        self, signal_name: str, handler: Callable[[object], None], owner: object | None = None
    ) -> None:
        del signal_name, handler, owner

    def emit(self, signal_name: str, payload: object) -> None:
        del signal_name, payload


class _FakeResultsStore:
    """An in-memory store honouring only the subset of `ResultsStore` this
    test needs: seed-then-read-back via `list_results`/`update_result`."""

    def __init__(self, initial: tuple[BenchmarkResult, ...]) -> None:
        self._rows = {row.result_id: row for row in initial}

    def list_results(self, run_id: int) -> tuple[BenchmarkResult, ...]:
        del run_id
        return tuple(self._rows.values())

    def update_result(self, result_id: ResultId, patch: ResultPatch) -> None:
        current = self._rows[result_id]
        changes = {
            field: getattr(patch, field)
            for field in patch.__struct_fields__
            if getattr(patch, field) is not None
        }
        self._rows[result_id] = msgspec.structs.replace(current, **changes)

    def final_row(self, result_id: ResultId) -> BenchmarkResult:
        return self._rows[result_id]


class _CountingChatStream:
    """A minimal `ChatStream` double yielding one canned chunk, then a response."""

    def __init__(self) -> None:
        self._chunks: tuple[ChatChunk, ...] = (
            ChatChunk(content=_SEEDED_SANITIZED_RESPONSE, delta_tokens=5),
        )
        self._response = ChatResponse(
            text=_SEEDED_SANITIZED_RESPONSE,
            total_time_ms=500,
            ttft_ms=100,
            prompt_tokens=10,
            completion_tokens=5,
        )

    def __iter__(self) -> "_CountingChatStream":
        return self

    def __next__(self) -> ChatChunk:
        if self._chunks:
            chunk, self._chunks = self._chunks[0], self._chunks[1:]
            return chunk
        raise StopIteration

    def trailing_response(self) -> ChatResponse:
        return self._response


class _CountingLLMClient:
    """An `LLMClient` double counting `chat_stream` invocations."""

    def __init__(self) -> None:
        self.chat_stream_call_count = 0

    def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> ChatStream:
        del request, token
        self.chat_stream_call_count += 1
        return _CountingChatStream()


class _CountingProviderRegistry:
    def __init__(self, client: _CountingLLMClient) -> None:
        self._client = client

    def list_enabled(self) -> tuple[object, ...]:
        return ()

    def get_client(self, provider_id: str) -> LLMClient:
        del provider_id
        return self._client  # type: ignore[return-value]  # structurally satisfies LLMClient


class _CountingSanityChecker:
    def __init__(self) -> None:
        self.call_count = 0

    def check(self, *, response: str, task: BenchmarkTask) -> bool:
        del response, task
        self.call_count += 1
        return True


class _CountingKeywordEvaluator:
    def __init__(self) -> None:
        self.call_count = 0

    def evaluate(self, *, response: str, required_terms: object) -> KeywordPhaseResult:
        del response, required_terms
        self.call_count += 1
        return KeywordPhaseResult(verdict=Verdict.PASS, terms=())


class _CountingCosineEvaluator:
    def __init__(self) -> None:
        self.call_count = 0

    def evaluate(
        self, *, response: str, golden_answer: str | None, cosine_enabled: bool
    ) -> CosinePhaseResult:
        del response, golden_answer, cosine_enabled
        self.call_count += 1
        return CosinePhaseResult(verdict=Verdict.PASS, similarity=_SEEDED_COSINE_SIMILARITY)


class _CountingJudgeEvaluator:
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
        return JudgePhaseResult(
            outcome=JudgePhaseOutcome.RESOLVED,
            verdict=Verdict.PASS,
            reasoning="ok",
            time_ms=100,
            completion_tokens=10,
        )


class _FakeSettingsService:
    def __init__(self, run: BenchmarkRun) -> None:
        self._values = {entry.setting_key: entry.setting_value for entry in run.settings_snapshot}

    def get_int(self, key: str, run: BenchmarkRun | None = None) -> int:
        del run
        return int(self._values[key])

    def get_bool(self, key: str, run: BenchmarkRun | None = None) -> bool:
        del run
        return self._values.get(key, "true").strip().lower() == "true"


class _Collaborators:
    """Bundles every fake collaborator one `run_all_phases` drive needs
    (test-only helper, not a msgspec/dataclass boundary type)."""

    def __init__(self, run: BenchmarkRun) -> None:
        self.sanity_checker = _CountingSanityChecker()
        self.keyword_evaluator = _CountingKeywordEvaluator()
        self.cosine_evaluator = _CountingCosineEvaluator()
        self.judge_evaluator = _CountingJudgeEvaluator()
        self.llm_client = _CountingLLMClient()
        self.provider_registry = _CountingProviderRegistry(self.llm_client)
        self.settings_service = _FakeSettingsService(run)
        self.bus = _RecordingBus()
        self.adaptive_timeout: AdaptiveTimeoutService = make_adaptive_timeout_service(
            snapshot=run.settings_snapshot
        )
        self.circuit_breaker: ProviderCircuitBreaker = make_circuit_breaker(
            snapshot=run.settings_snapshot, clock=FakeClock()
        )


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
        settings_snapshot=_STABILITY_SETTINGS,
    )


def _drive_run_all_phases(
    *, run: BenchmarkRun, row: BenchmarkResult, collaborators: _Collaborators
) -> BenchmarkResult:
    """Drive `run_all_phases` over one seeded row, returning its final persisted state."""
    results_store = _FakeResultsStore((row,))
    task = make_task(task_id=row.task_id, golden_answer="Paris", cosine_enabled=True)
    tasks_by_id = {row.task_id: task}
    token = make_cancellation_token()
    state = StabilityRunState()
    stability_collaborators = StabilityCollaborators(
        bus=collaborators.bus,  # type: ignore[arg-type]  # structurally satisfies EventBus
        clock=FakeClock(),
        provider_registry=collaborators.provider_registry,  # type: ignore[arg-type]
        results_store=results_store,  # type: ignore[arg-type]
        settings_service=collaborators.settings_service,  # type: ignore[arg-type]
        task_runner=_InlineTaskRunner(),
    )

    def _unit_factory_for_phase(phase: Phase, result: BenchmarkResult) -> Callable[[], ResultPatch]:
        if phase is Phase.KEYWORD_CHECK:
            return build_keyword_unit(
                result=result,
                task=tasks_by_id[result.task_id],
                evaluator=collaborators.keyword_evaluator,
                cosine_enabled=True,
                judge_enabled=True,
                force_judge_on_prior_failure=False,
            )
        if phase is Phase.COSINE_CHECK:
            return build_cosine_unit(
                result=result,
                task=tasks_by_id[result.task_id],
                evaluator=collaborators.cosine_evaluator,
                judge_enabled=True,
                force_judge_on_prior_failure=False,
            )
        message = f"unreachable phase {phase!r} for this test's unit_factory_for_phase"
        raise AssertionError(message)

    def _stability_phase_runner(
        phase: Phase, groups: tuple[tuple[str, str, tuple[BenchmarkResult, ...]], ...]
    ) -> None:
        run_stability_phase(
            phase=phase,
            groups=groups,
            run=run,
            tasks_by_id=tasks_by_id,
            sanity_checker=collaborators.sanity_checker,
            judge_evaluator=collaborators.judge_evaluator,
            token=token,
            keyword_enabled=True,
            cosine_enabled=True,
            judge_enabled=True,
            force_judge_on_prior_failure=False,
            collaborators=stability_collaborators,
            state=state,
            adaptive_timeout=collaborators.adaptive_timeout,
            circuit_breaker=collaborators.circuit_breaker,
            retry_count=0,
            warmup_enabled=False,
        )

    run_all_phases(
        run_mode=run.run_mode,
        keyword_enabled=True,
        cosine_enabled=True,
        judge_enabled=True,
        run_id=run.run_id,
        runner=_InlineTaskRunner(),
        token=token,
        results_store=results_store,  # type: ignore[arg-type]  # structurally satisfies ResultsStore
        unit_factory_for_phase=_unit_factory_for_phase,
        stability_phase_runner=_stability_phase_runner,
    )
    return results_store.final_row(row.result_id)


@pytest.mark.parametrize(
    ("reset_status", "expected_inference_calls", "expected_judge_calls"),
    [
        (ResultStatus.PENDING, 1, 1),
        (ResultStatus.AWAITING_JUDGE_CHECK, 0, 1),
    ],
)
def test_retry_re_entry_by_reset_status(
    reset_status: ResultStatus, expected_inference_calls: int, expected_judge_calls: int
) -> None:
    """Proves: STORY-030-AC-5

    A result row seeded directly at `reset_status` re-enters `run_all_phases`
    and runs exactly the phases the reset status implies: `PENDING` re-runs
    inference (and every later phase); `AWAITING_JUDGE_CHECK` runs only the
    judge — its pre-seeded `sanitized_response`/`keyword_verdict`/
    `cosine_similarity` are reused, never recomputed, and the fake
    `LLMClient`'s inference-call count stays zero.
    """
    run = _make_run()
    row = make_benchmark_result(
        result_id=1,
        task_id="task-1",
        provider_id=_TEST_PROVIDER_ID,
        model_name=_TEST_MODEL_NAME,
        status=reset_status,
    )
    if reset_status is ResultStatus.AWAITING_JUDGE_CHECK:
        row = msgspec.structs.replace(
            row,
            sanitized_response=_SEEDED_SANITIZED_RESPONSE,
            sanity_check_passed=True,
            keyword_verdict=Verdict.PASS,
            cosine_verdict=Verdict.PASS,
            cosine_similarity=_SEEDED_COSINE_SIMILARITY,
        )
    collaborators = _Collaborators(run)

    final_row = _drive_run_all_phases(run=run, row=row, collaborators=collaborators)

    assert collaborators.llm_client.chat_stream_call_count == expected_inference_calls
    assert collaborators.judge_evaluator.call_count == expected_judge_calls
    assert final_row.status is ResultStatus.COMPLETED
    assert final_row.verdict is Verdict.PASS
    if reset_status is ResultStatus.AWAITING_JUDGE_CHECK:
        # The pre-seeded upstream fields are byte-identical to the seeded
        # values — never recomputed by this re-entry.
        assert final_row.sanitized_response == _SEEDED_SANITIZED_RESPONSE
        assert final_row.cosine_similarity == _SEEDED_COSINE_SIMILARITY
        assert collaborators.keyword_evaluator.call_count == 0
        assert collaborators.cosine_evaluator.call_count == 0


def test_failed_judge_timeout_retry_reruns_whole_task() -> None:
    """Proves: STORY-030-AC-5

    A row reset from FAILED_JUDGE_TIMEOUT to PENDING (DD-34's whole-task retry
    class) re-enters at Phase 2 (inference) and recomputes every phase's
    output — the fake LLMClient's inference-call count increments by exactly
    one for this row, proving the original attempt's data was not reused.
    """
    run = _make_run()
    # The row's reset status is what the Retry/Resume use case would have
    # produced for a `FAILED_JUDGE_TIMEOUT` row selected for retry (DD-34) —
    # this test names that origin explicitly, even though the pipeline's own
    # re-entry logic treats it identically to any other `PENDING` row.
    row = make_benchmark_result(
        result_id=1,
        task_id="task-1",
        provider_id=_TEST_PROVIDER_ID,
        model_name=_TEST_MODEL_NAME,
        status=ResultStatus.PENDING,
    )
    collaborators = _Collaborators(run)

    final_row = _drive_run_all_phases(run=run, row=row, collaborators=collaborators)

    assert collaborators.llm_client.chat_stream_call_count == 1
    assert collaborators.keyword_evaluator.call_count == 1
    assert collaborators.cosine_evaluator.call_count == 1
    assert collaborators.judge_evaluator.call_count == 1
    assert final_row.status is ResultStatus.COMPLETED
