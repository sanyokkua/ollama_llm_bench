"""Proves: STORY-029-AC-1

Direct smoke tests for the four phase-unit builder families — the fuller
end-to-end exercise happens via Task 6's dispatcher integration tests; these
tests confirm each builder's own success-path `ResultPatch` shape in
isolation, against `mocker.Mock(spec=...)` collaborators.

`build_inference_attempt`/`finalize_inference_success` and
`build_judge_attempt`/`finalize_judge_success` are the STORY-030 split of the
pre-STORY-030 single-attempt `build_inference_unit`/`build_judge_unit` — each
pair is exercised here as attempt-builder-then-finalize, mirroring exactly how
`_internal.stability_dispatch.run_task_with_stability` drives them in
production.
"""

from collections.abc import Iterator

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.benchmark_pipeline._internal.units import (
    _InferenceAttemptOutcome,
    build_cosine_unit,
    build_inference_attempt,
    build_judge_attempt,
    build_judge_timeout_exhausted_patch,
    build_keyword_unit,
    finalize_inference_success,
    finalize_judge_success,
)
from ollama_llm_bench.backend.benchmark_pipeline.testing import make_benchmark_result
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import (
    FakeClock,
    make_cancellation_token,
    make_task,
)
from ollama_llm_bench.backend.domain.models import (
    BenchmarkResult,
    ChatChunk,
    ChatResponse,
    ErrorKind,
    ResolutionLayer,
    ResultStatus,
    RunMode,
    Verdict,
)
from ollama_llm_bench.backend.evaluation.models import (
    CosinePhaseResult,
    JudgePhaseOutcome,
    JudgePhaseResult,
    KeywordPhaseResult,
)
from ollama_llm_bench.backend.evaluation.protocols import (
    CosineEvaluator,
    JudgeEvaluator,
    KeywordEvaluator,
    SanityChecker,
)
from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.provider_registry.protocols import ChatStream, ProviderRegistry

_JUDGE_STARTED_AND_COMPLETED_EMIT_COUNT = 2
_JUDGE_PROVIDER_ID = "22222222-2222-4222-8222-222222222222"
_JUDGE_MODEL_NAME = "judge-model"


class _FakeChatStream:
    """A minimal `ChatStream` double: yields canned chunks, then a trailing response."""

    def __init__(self, *, chunks: tuple[ChatChunk, ...], response: ChatResponse) -> None:
        self._chunks = chunks
        self._response = response

    def __iter__(self) -> Iterator[ChatChunk]:
        return iter(self._chunks)

    def __next__(self) -> ChatChunk:  # pragma: no cover — iteration goes via __iter__
        raise StopIteration

    def trailing_response(self) -> ChatResponse:
        return self._response


def test_build_keyword_unit_advances_to_awaiting_cosine_check(mocker: MockerFixture) -> None:
    """Proves: STORY-029-AC-1

    A successful keyword-phase evaluation, with cosine enabled, advances
    the row to AWAITING_COSINE_CHECK with no combined verdict yet.
    """
    result = make_benchmark_result(status=ResultStatus.AWAITING_KEYWORD_CHECK)
    evaluator = mocker.Mock(spec=KeywordEvaluator)
    evaluator.evaluate.return_value = KeywordPhaseResult(verdict=Verdict.PASS, terms=())

    unit = build_keyword_unit(
        result=result,
        task=make_task(),
        evaluator=evaluator,
        cosine_enabled=True,
        judge_enabled=False,
        force_judge_on_prior_failure=False,
    )
    patch = unit()

    assert patch.status is ResultStatus.AWAITING_COSINE_CHECK
    assert patch.keyword_verdict is Verdict.PASS
    assert patch.verdict is None


def test_build_cosine_unit_completes_when_judge_disabled(mocker: MockerFixture) -> None:
    """Proves: STORY-029-AC-1

    A successful cosine-phase evaluation, with judge disabled, is this
    row's terminal grading phase — it completes with a combined verdict.
    """
    result = BenchmarkResult(
        result_id=1,
        run_id=1,
        task_id="task-1",
        provider_id="11111111-1111-4111-8111-111111111111",
        provider_name="Test Provider",
        model_name="llama3",
        status=ResultStatus.AWAITING_COSINE_CHECK,
        created_at="2026-01-01T00:00:00Z",
        sanity_check_passed=True,
        keyword_verdict=Verdict.PASS,
    )
    evaluator = mocker.Mock(spec=CosineEvaluator)
    evaluator.evaluate.return_value = CosinePhaseResult(verdict=Verdict.PASS, similarity=0.9)

    unit = build_cosine_unit(
        result=result,
        task=make_task(),
        evaluator=evaluator,
        judge_enabled=False,
        force_judge_on_prior_failure=False,
    )
    patch = unit()

    assert patch.status is ResultStatus.COMPLETED
    assert patch.cosine_verdict is Verdict.PASS
    assert patch.verdict is Verdict.PASS
    assert patch.resolution_layer is ResolutionLayer.COSINE


def test_build_judge_attempt_then_finalize_completes_with_resolved_outcome(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-029-AC-1

    A resolved judge-phase evaluation always completes the row (the judge
    phase is always the terminal grading phase when it runs) — driven
    through the STORY-030 attempt-builder-then-finalize split exactly as
    `run_task_with_stability` drives it in production.
    """
    result = BenchmarkResult(
        result_id=1,
        run_id=1,
        task_id="task-1",
        provider_id="11111111-1111-4111-8111-111111111111",
        provider_name="Test Provider",
        model_name="llama3",
        status=ResultStatus.AWAITING_JUDGE_CHECK,
        created_at="2026-01-01T00:00:00Z",
        sanity_check_passed=True,
    )
    evaluator = mocker.Mock(spec=JudgeEvaluator)
    evaluator.evaluate.return_value = JudgePhaseResult(
        outcome=JudgePhaseOutcome.RESOLVED,
        verdict=Verdict.PASS,
        reasoning="Matches the golden answer.",
        time_ms=1200,
        completion_tokens=42,
    )
    bus = mocker.Mock(spec=EventBus)

    build_attempt = build_judge_attempt(
        result=result,
        task=make_task(),
        evaluator=evaluator,
        token=make_cancellation_token(),
        bus=bus,
        judge_provider_id=_JUDGE_PROVIDER_ID,
        judge_model_name=_JUDGE_MODEL_NAME,
    )
    attempt = build_attempt(30_000)
    raw = attempt()
    finalize = finalize_judge_success(result=result, force_judge_on_prior_failure=False, bus=bus)
    patch = finalize(raw)

    assert patch.status is ResultStatus.COMPLETED
    assert patch.judge_verdict is Verdict.PASS
    assert patch.verdict is Verdict.PASS
    assert patch.resolution_layer is ResolutionLayer.JUDGE
    assert bus.emit.call_count == _JUDGE_STARTED_AND_COMPLETED_EMIT_COUNT


def test_build_judge_attempt_emits_started_with_run_judge_target_not_row_test_model(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-030 (Task 1 judge-target fix)

    `JudgeStartedEvent.judge_provider_id`/`judge_model_name` equal the run's
    resolved judge target passed to `build_judge_attempt`, not the row's own
    `provider_id`/`model_name` (a different test model in this scenario) —
    the mislabeling `build_judge_unit` had before this story's fix.
    """
    result = make_benchmark_result(
        status=ResultStatus.AWAITING_JUDGE_CHECK,
        provider_id="11111111-1111-4111-8111-111111111111",
        model_name="llama3",
    )
    evaluator = mocker.Mock(spec=JudgeEvaluator)
    evaluator.evaluate.return_value = JudgePhaseResult(
        outcome=JudgePhaseOutcome.RESOLVED,
        verdict=Verdict.PASS,
        reasoning="ok",
        time_ms=100,
        completion_tokens=10,
    )
    bus = mocker.Mock(spec=EventBus)

    build_judge_attempt(
        result=result,
        task=make_task(),
        evaluator=evaluator,
        token=make_cancellation_token(),
        bus=bus,
        judge_provider_id=_JUDGE_PROVIDER_ID,
        judge_model_name=_JUDGE_MODEL_NAME,
    )

    started_call = bus.emit.call_args_list[0]
    started_payload = started_call.args[1]
    assert started_payload.judge_provider_id == _JUDGE_PROVIDER_ID
    assert started_payload.judge_model_name == _JUDGE_MODEL_NAME
    assert started_payload.judge_provider_id != result.provider_id
    assert started_payload.judge_model_name != result.model_name


def test_finalize_judge_success_maps_transport_failure_to_generic_errored(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-029-AC-1

    A TRANSPORT_FAILURE outcome maps to a generic ERRORED patch, never the
    STORY-030-owned FAILED_JUDGE_TIMEOUT status.
    """
    result = make_benchmark_result(status=ResultStatus.AWAITING_JUDGE_CHECK)
    raw = JudgePhaseResult(
        outcome=JudgePhaseOutcome.TRANSPORT_FAILURE,
        verdict=None,
        reasoning="the provider connection failed",
        time_ms=500,
        completion_tokens=None,
    )
    bus = mocker.Mock(spec=EventBus)

    finalize = finalize_judge_success(result=result, force_judge_on_prior_failure=False, bus=bus)
    patch = finalize(raw)

    assert patch.status is ResultStatus.ERRORED


def test_build_judge_timeout_exhausted_patch_settles_failed_judge_timeout() -> None:
    """Proves: STORY-030-AC-3

    The per-task judge-timeout-ladder exhaustion terminal patch settles
    FAILED_JUDGE_TIMEOUT with error_kind=JUDGE_TIMEOUT and no combined
    verdict — the combination step is not applied.
    """
    build_patch = build_judge_timeout_exhausted_patch()

    patch = build_patch()

    assert patch.status is ResultStatus.FAILED_JUDGE_TIMEOUT
    assert patch.error_kind is ErrorKind.JUDGE_TIMEOUT
    assert patch.verdict is None
    assert patch.resolution_layer is None


def test_build_inference_attempt_then_finalize_advances_to_completed(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-029-AC-1

    A successful inference call in a GRADED run with every grading toggle
    disabled routes straight to COMPLETED with no verdict — driven through
    the STORY-030 attempt-builder-then-finalize split exactly as
    `run_task_with_stability` drives it in production.
    """
    result = make_benchmark_result(status=ResultStatus.PENDING)
    chat_stream: ChatStream = _FakeChatStream(
        chunks=(ChatChunk(content="Paris.", delta_tokens=3),),
        response=ChatResponse(
            text="Paris.", total_time_ms=500, ttft_ms=100, prompt_tokens=10, completion_tokens=3
        ),
    )
    client = mocker.Mock()
    client.chat_stream.return_value = chat_stream
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.return_value = client
    sanity_checker = mocker.Mock(spec=SanityChecker)
    sanity_checker.check.return_value = True
    bus = mocker.Mock(spec=EventBus)
    task = make_task()

    build_attempt = build_inference_attempt(
        result=result,
        task=task,
        provider_registry=provider_registry,
        sanity_checker=sanity_checker,
        clock=FakeClock(),
        bus=bus,
        token=make_cancellation_token(),
    )
    attempt = build_attempt(30_000)
    outcome = attempt()
    finalize = finalize_inference_success(
        result=result,
        task=task,
        bus=bus,
        run_mode=RunMode.GRADED,
        keyword_enabled=False,
        cosine_enabled=False,
        judge_enabled=False,
    )
    patch = finalize(outcome)

    assert patch.status is ResultStatus.COMPLETED
    assert patch.sanitized_response == "Paris."
    assert patch.verdict is None
    assert patch.resolution_layer is ResolutionLayer.SKIP


def _make_inference_outcome(
    mocker: MockerFixture, *, result: BenchmarkResult
) -> _InferenceAttemptOutcome:
    """Drive one successful inference attempt over mocked collaborators."""
    chat_stream: ChatStream = _FakeChatStream(
        chunks=(ChatChunk(content="Paris.", delta_tokens=3),),
        response=ChatResponse(
            text="Paris.", total_time_ms=500, ttft_ms=100, prompt_tokens=10, completion_tokens=3
        ),
    )
    client = mocker.Mock()
    client.chat_stream.return_value = chat_stream
    provider_registry = mocker.Mock(spec=ProviderRegistry)
    provider_registry.get_client.return_value = client
    sanity_checker = mocker.Mock(spec=SanityChecker)
    sanity_checker.check.return_value = True
    build_attempt = build_inference_attempt(
        result=result,
        task=make_task(),
        provider_registry=provider_registry,
        sanity_checker=sanity_checker,
        clock=FakeClock(),
        bus=mocker.Mock(spec=EventBus),
        token=make_cancellation_token(),
    )
    return build_attempt(30_000)()


@pytest.mark.parametrize("run_mode", [RunMode.SYNTHETIC, RunMode.TASKS])
def test_finalize_inference_success_completes_non_grading_mode_with_all_toggles_enabled(
    mocker: MockerFixture, run_mode: RunMode
) -> None:
    """Proves: STORY-086-AC-5

    A non-grading run completes at inference even with every toggle on.

    Regression test for the live defect STORY-086's opt-in tier found: `eval.phase_keyword_enabled` and
    `eval.phase_cosine_enabled` default to true and are read for every run
    regardless of mode, so a plain SYNTHETIC/TASKS run used to route its rows
    into AWAITING_KEYWORD_CHECK — a phase `_internal.grouping.phase_applies`
    refuses to execute outside GRADED. The rows parked there forever and the
    run could never settle COMPLETED. 08-B §5.1 puts the mode gate on the
    transition itself: `RUNNING_INFERENCE --> COMPLETED: inference succeeded,
    mode does not grade`, with `verdict` unset (08-B §5) and
    `ResolutionLayer.SKIP` — "the run mode did not grade; no verdict was
    produced" (10/02_DTOS_AND_ENUMS §4.5).
    """
    result = make_benchmark_result(status=ResultStatus.PENDING)
    outcome = _make_inference_outcome(mocker, result=result)

    finalize = finalize_inference_success(
        result=result,
        task=make_task(),
        bus=mocker.Mock(spec=EventBus),
        run_mode=run_mode,
        keyword_enabled=True,
        cosine_enabled=True,
        judge_enabled=True,
    )
    patch = finalize(outcome)

    assert (patch.status, patch.verdict, patch.resolution_layer) == (
        ResultStatus.COMPLETED,
        None,
        ResolutionLayer.SKIP,
    )
