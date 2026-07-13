"""Proves: STORY-029-AC-1

Direct smoke tests for the four `build_*_unit` functions — the fuller
end-to-end exercise happens via Task 6's dispatcher integration tests; these
tests confirm each builder's own success-path `ResultPatch` shape in
isolation, against `mocker.Mock(spec=...)` collaborators.
"""

from collections.abc import Iterator

from pytest_mock import MockerFixture

from ollama_llm_bench.backend.benchmark_pipeline._internal.units import (
    build_cosine_unit,
    build_inference_unit,
    build_judge_unit,
    build_keyword_unit,
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
    ResolutionLayer,
    ResultStatus,
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

_JUDGE_UNIT_EMIT_COUNT = 2


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


def test_build_judge_unit_completes_with_resolved_outcome(mocker: MockerFixture) -> None:
    """Proves: STORY-029-AC-1

    A resolved judge-phase evaluation always completes the row (the judge
    phase is always the terminal grading phase when it runs).
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

    unit = build_judge_unit(
        result=result,
        task=make_task(),
        evaluator=evaluator,
        timeout_ms=30_000,
        token=make_cancellation_token(),
        bus=bus,
        force_judge_on_prior_failure=False,
    )
    patch = unit()

    assert patch.status is ResultStatus.COMPLETED
    assert patch.judge_verdict is Verdict.PASS
    assert patch.verdict is Verdict.PASS
    assert patch.resolution_layer is ResolutionLayer.JUDGE
    assert bus.emit.call_count == _JUDGE_UNIT_EMIT_COUNT  # _judge_started + _judge_completed


def test_build_judge_unit_maps_transport_failure_to_generic_errored(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-029-AC-1

    A TRANSPORT_FAILURE outcome maps to a generic ERRORED patch, never the
    STORY-030-owned FAILED_JUDGE_TIMEOUT status.
    """
    result = make_benchmark_result(status=ResultStatus.AWAITING_JUDGE_CHECK)
    evaluator = mocker.Mock(spec=JudgeEvaluator)
    evaluator.evaluate.return_value = JudgePhaseResult(
        outcome=JudgePhaseOutcome.TRANSPORT_FAILURE,
        verdict=None,
        reasoning="the provider connection failed",
        time_ms=500,
        completion_tokens=None,
    )
    bus = mocker.Mock(spec=EventBus)

    unit = build_judge_unit(
        result=result,
        task=make_task(),
        evaluator=evaluator,
        timeout_ms=30_000,
        token=make_cancellation_token(),
        bus=bus,
        force_judge_on_prior_failure=False,
    )
    patch = unit()

    assert patch.status is ResultStatus.ERRORED


def test_build_inference_unit_advances_to_completed_when_no_grading_enabled(
    mocker: MockerFixture,
) -> None:
    """Proves: STORY-029-AC-1

    A successful inference call in a non-grading mode (every grading
    toggle disabled) routes straight to COMPLETED with no verdict.
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

    unit = build_inference_unit(
        result=result,
        task=make_task(),
        provider_registry=provider_registry,
        sanity_checker=sanity_checker,
        timeout_ms=30_000,
        clock=FakeClock(),
        bus=bus,
        token=make_cancellation_token(),
        keyword_enabled=False,
        cosine_enabled=False,
        judge_enabled=False,
    )
    patch = unit()

    assert patch.status is ResultStatus.COMPLETED
    assert patch.sanitized_response == "Paris."
    assert patch.verdict is None
    assert patch.resolution_layer is ResolutionLayer.SKIP
