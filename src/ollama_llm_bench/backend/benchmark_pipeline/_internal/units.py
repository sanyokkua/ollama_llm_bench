"""Per-phase-per-task unit callables submitted to the `TaskRunner` (08-B §5.1, §3).

Each `build_*_unit` function closes over its already-constructed collaborators and
returns a nullary `Callable[[], ResultPatch]` the dispatcher (Task 6) submits to the
`TaskRunner`, blocks on, and persists. No unit performs database I/O or emits a
run-domain event (DD-41) — a unit only returns the `ResultPatch`; the two per-task
events this module emits directly (`_inference_started`/`_inference_completed`,
`_judge_started`/`_judge_completed`) are per-task, not run-domain, events, matching
Task 8's existing wrapper set.
"""

from collections.abc import Callable
import math
import re
from typing import Final

from ollama_llm_bench.backend.benchmark_pipeline._internal.containment import contain_unit_failure
from ollama_llm_bench.backend.benchmark_pipeline._internal.events import (
    emit_inference_completed,
    emit_inference_started,
    emit_judge_completed,
    emit_judge_started,
)
from ollama_llm_bench.backend.benchmark_pipeline._internal.progress import emit_progress_during
from ollama_llm_bench.backend.benchmark_pipeline.models import Phase
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import (
    BenchmarkResult,
    BenchmarkTask,
    ChatMessage,
    ChatRequest,
    ChatRole,
    DurationMs,
    ErrorKind,
    InferenceContext,
    ResolutionLayer,
    ResultPatch,
    ResultStatus,
    Verdict,
)
from ollama_llm_bench.backend.errors import AppError, TaskCancelledError
from ollama_llm_bench.backend.evaluation import combine_verdict
from ollama_llm_bench.backend.evaluation.models import JudgePhaseOutcome
from ollama_llm_bench.backend.evaluation.protocols import (
    CosineEvaluator,
    JudgeEvaluator,
    KeywordEvaluator,
    SanityChecker,
)
from ollama_llm_bench.backend.events.models import (
    InferenceCompletedEvent,
    InferenceStartedEvent,
    JudgeCompletedEvent,
    JudgeStartedEvent,
)
from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry

__all__: list[str] = [
    "build_cosine_unit",
    "build_inference_unit",
    "build_judge_unit",
    "build_keyword_unit",
]

_ESTIMATE_CHARS_PER_TOKEN = 4
_MS_PER_SECOND = 1000

_THINKING_BLOCK_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"<think(?:ing)?>.*?</think(?:ing)?>", re.IGNORECASE | re.DOTALL
)

_GRADING_PHASES_AFTER: Final[dict[Phase, tuple[Phase, ...]]] = {
    Phase.INFERENCE: (Phase.KEYWORD_CHECK, Phase.COSINE_CHECK, Phase.JUDGE_CHECK),
    Phase.KEYWORD_CHECK: (Phase.COSINE_CHECK, Phase.JUDGE_CHECK),
    Phase.COSINE_CHECK: (Phase.JUDGE_CHECK,),
    Phase.JUDGE_CHECK: (),
}
"""Which later grading phases could follow a given completed phase, in phase order."""

_AWAITING_STATUS_FOR_PHASE: Final[dict[Phase, ResultStatus]] = {
    Phase.KEYWORD_CHECK: ResultStatus.AWAITING_KEYWORD_CHECK,
    Phase.COSINE_CHECK: ResultStatus.AWAITING_COSINE_CHECK,
    Phase.JUDGE_CHECK: ResultStatus.AWAITING_JUDGE_CHECK,
}
"""The non-terminal status a row enters when routed into a given grading phase."""


def _next_status_after_phase(
    *, completed_phase: Phase, keyword_enabled: bool, cosine_enabled: bool, judge_enabled: bool
) -> ResultStatus | None:
    """Return the next `AWAITING_*` status after `completed_phase` (08-B §5.1).

    Args:
        completed_phase: The phase that just finished for this row.
        keyword_enabled: Whether the keyword phase is enabled for this run.
        cosine_enabled: Whether the cosine phase is enabled for this run.
        judge_enabled: Whether the judge phase is enabled for this run.

    Returns:
        The next `AWAITING_*` status to route into, or `None` when no later
        grading phase is enabled — the caller then routes to `COMPLETED`.
    """
    enabled_by_phase = {
        Phase.KEYWORD_CHECK: keyword_enabled,
        Phase.COSINE_CHECK: cosine_enabled,
        Phase.JUDGE_CHECK: judge_enabled,
    }
    for phase in _GRADING_PHASES_AFTER[completed_phase]:
        if enabled_by_phase[phase]:
            return _AWAITING_STATUS_FOR_PHASE[phase]
    return None


def _complete_or_advance(  # noqa: PLR0913  # each parameter disambiguates a distinct
    # routing/combination input (the completed phase, the three per-run grading
    # toggles, the sanity outcome, the three accumulated per-phase verdicts, and the
    # force-judge setting) — mirrors combine_verdict_impl's own flat-parameter design
    *,
    completed_phase: Phase,
    keyword_enabled: bool,
    cosine_enabled: bool,
    judge_enabled: bool,
    sanity_check_passed: bool,
    keyword_verdict: Verdict | None,
    cosine_verdict: Verdict | None,
    judge_verdict: Verdict | None,
    force_judge_on_prior_failure: bool,
) -> tuple[ResultStatus, Verdict | None, ResolutionLayer | None]:
    """Decide the next status and, only on the terminal grading phase, the verdict.

    Args:
        completed_phase: The phase that just finished for this row.
        keyword_enabled: Whether the keyword phase is enabled for this run.
        cosine_enabled: Whether the cosine phase is enabled for this run.
        judge_enabled: Whether the judge phase is enabled for this run.
        sanity_check_passed: The sanity pre-check's outcome for this row.
        keyword_verdict: The keyword phase's accumulated verdict, or `None`.
        cosine_verdict: The cosine phase's accumulated verdict, or `None`.
        judge_verdict: The judge phase's accumulated verdict, or `None`.
        force_judge_on_prior_failure: The run's force-judge setting.

    Returns:
        A `(status, verdict, resolution_layer)` triple. `verdict` and
        `resolution_layer` are both `None` unless `status` is `COMPLETED`.
    """
    next_status = _next_status_after_phase(
        completed_phase=completed_phase,
        keyword_enabled=keyword_enabled,
        cosine_enabled=cosine_enabled,
        judge_enabled=judge_enabled,
    )
    if next_status is not None:
        return next_status, None, None
    if not (keyword_enabled or cosine_enabled or judge_enabled):
        return ResultStatus.COMPLETED, None, ResolutionLayer.SKIP
    combined = combine_verdict(
        sanity_check_passed=sanity_check_passed,
        keyword_verdict=keyword_verdict,
        cosine_verdict=cosine_verdict,
        judge_enabled=judge_enabled,
        judge_verdict=judge_verdict,
        force_judge_on_prior_failure=force_judge_on_prior_failure,
    )
    return ResultStatus.COMPLETED, combined.verdict, combined.resolution_layer


def _sanitize_response(raw_response: str) -> tuple[str, bool]:
    """Strip a reasoning/thinking block from a model response.

    A minimal, self-contained sanitizer: no dedicated stripping algorithm is
    specified elsewhere in this codebase or its spec (verified: no
    `sanitized_response` producer exists anywhere else in the repository).
    Matches the common `<think>...</think>` / `<thinking>...</thinking>`
    convention used by reasoning models (e.g. DeepSeek-R1, QwQ); a model whose
    reasoning block uses a different convention is not stripped by this pass.

    Args:
        raw_response: The unmodified text returned by the model.

    Returns:
        The sanitized text (stripped of surrounding whitespace) and whether a
        thinking block was found and removed.
    """
    sanitized, count = _THINKING_BLOCK_PATTERN.subn("", raw_response)
    return sanitized.strip(), count > 0


def build_keyword_unit(  # noqa: PLR0913  # one parameter per distinct collaborator
    # (the row, the task, the evaluator) plus the three routing inputs the phase's
    # own ResultPatch cannot compute without
    *,
    result: BenchmarkResult,
    task: BenchmarkTask,
    evaluator: KeywordEvaluator,
    cosine_enabled: bool,
    judge_enabled: bool,
    force_judge_on_prior_failure: bool,
) -> Callable[[], ResultPatch]:
    """Build the Phase-3 (keyword) unit callable for one result row.

    Args:
        result: The row's currently persisted state (carries no prior
            grading verdicts at this phase).
        task: The frozen task supplying the required-terms lists.
        evaluator: The run's constructed `KeywordEvaluator`.
        cosine_enabled: Whether the cosine phase is enabled for this run.
        judge_enabled: Whether the judge phase is enabled for this run.
        force_judge_on_prior_failure: The run's force-judge setting.

    Returns:
        A nullary callable returning the phase's `ResultPatch`, never
        raising `AppError` (contained) or propagating anything but
        `TaskCancelledError`.
    """

    def _run() -> ResultPatch:
        try:
            evaluation = evaluator.evaluate(
                response=result.sanitized_response or "", required_terms=task.required_terms
            )
        except AppError as exc:
            if isinstance(exc, TaskCancelledError):
                raise
            return contain_unit_failure(exc)
        status, verdict, resolution_layer = _complete_or_advance(
            completed_phase=Phase.KEYWORD_CHECK,
            keyword_enabled=True,
            cosine_enabled=cosine_enabled,
            judge_enabled=judge_enabled,
            sanity_check_passed=result.sanity_check_passed or False,
            keyword_verdict=evaluation.verdict,
            cosine_verdict=result.cosine_verdict,
            judge_verdict=result.judge_verdict,
            force_judge_on_prior_failure=force_judge_on_prior_failure,
        )
        return ResultPatch(
            status=status,
            keyword_verdict=evaluation.verdict,
            terms=evaluation.terms,
            verdict=verdict,
            resolution_layer=resolution_layer,
        )

    return _run


def build_cosine_unit(
    *,
    result: BenchmarkResult,
    task: BenchmarkTask,
    evaluator: CosineEvaluator,
    judge_enabled: bool,
    force_judge_on_prior_failure: bool,
) -> Callable[[], ResultPatch]:
    """Build the Phase-4 (cosine) unit callable for one result row.

    Args:
        result: The row's currently persisted state, carrying the keyword
            phase's verdict when that phase ran.
        task: The frozen task supplying the golden answer and cosine opt-out.
        evaluator: The run's constructed `CosineEvaluator`.
        judge_enabled: Whether the judge phase is enabled for this run.
        force_judge_on_prior_failure: The run's force-judge setting.

    Returns:
        A nullary callable returning the phase's `ResultPatch`, never
        raising `AppError` (contained) or propagating anything but
        `TaskCancelledError`.
    """

    def _run() -> ResultPatch:
        try:
            evaluation = evaluator.evaluate(
                response=result.sanitized_response or "",
                golden_answer=task.golden_answer,
                cosine_enabled=task.cosine_enabled,
            )
        except AppError as exc:
            if isinstance(exc, TaskCancelledError):
                raise
            return contain_unit_failure(exc)
        status, verdict, resolution_layer = _complete_or_advance(
            completed_phase=Phase.COSINE_CHECK,
            keyword_enabled=True,
            cosine_enabled=True,
            judge_enabled=judge_enabled,
            sanity_check_passed=result.sanity_check_passed or False,
            keyword_verdict=result.keyword_verdict,
            cosine_verdict=evaluation.verdict,
            judge_verdict=result.judge_verdict,
            force_judge_on_prior_failure=force_judge_on_prior_failure,
        )
        return ResultPatch(
            status=status,
            cosine_verdict=evaluation.verdict,
            cosine_similarity=evaluation.similarity,
            verdict=verdict,
            resolution_layer=resolution_layer,
        )

    return _run


def build_judge_unit(  # noqa: PLR0913  # one parameter per distinct collaborator
    # (the row, the task, the evaluator, the token budget, the cancellation token,
    # the bus for this unit's own per-task events) plus the routing input the
    # phase's own ResultPatch cannot compute without
    *,
    result: BenchmarkResult,
    task: BenchmarkTask,
    evaluator: JudgeEvaluator,
    timeout_ms: DurationMs,
    token: CancellationToken,
    bus: EventBus,
    force_judge_on_prior_failure: bool,
) -> Callable[[], ResultPatch]:
    """Build the Phase-5 (judge) unit callable for one result row.

    Single attempt at a fixed `timeout_ms` — the adaptive-timeout budget,
    retry ladder, and judge-model-exclusion mechanics belong to STORY-030.

    Args:
        result: The row's currently persisted state, carrying the keyword
            and cosine phases' verdicts when those phases ran.
        task: The frozen task supplying question/criteria/context.
        evaluator: The run's constructed `JudgeEvaluator`.
        timeout_ms: The per-attempt call budget.
        token: The run's live `CancellationToken`, forwarded to the evaluator.
        bus: The application event bus, for the `_judge_started`/
            `_judge_completed` per-task events this unit emits directly.
        force_judge_on_prior_failure: The run's force-judge setting.

    Returns:
        A nullary callable returning the phase's `ResultPatch`, never
        raising `AppError` (contained) or propagating anything but
        `TaskCancelledError`.
    """

    def _run() -> ResultPatch:
        emit_judge_started(
            bus,
            JudgeStartedEvent(
                run_id=result.run_id,
                result_id=result.result_id,
                task_id=result.task_id,
                judge_provider_id=result.provider_id,
                judge_model_name=result.model_name,
            ),
        )
        try:
            evaluation = evaluator.evaluate(
                response=result.sanitized_response or "",
                system_prompt_sent=result.system_prompt_sent,
                task=task,
                timeout_ms=timeout_ms,
                token=token,
            )
        except AppError as exc:
            if isinstance(exc, TaskCancelledError):
                raise
            return contain_unit_failure(exc)
        if evaluation.outcome is not JudgePhaseOutcome.RESOLVED:
            return ResultPatch(
                status=ResultStatus.ERRORED,
                error_kind=ErrorKind.LLM,
                error_message=evaluation.reasoning,
            )
        emit_judge_completed(
            bus,
            JudgeCompletedEvent(
                run_id=result.run_id,
                result_id=result.result_id,
                task_id=result.task_id,
                judge_verdict=evaluation.verdict or Verdict.FAIL,
                judge_reasoning=evaluation.reasoning,
                judge_time_ms=evaluation.time_ms,
                judge_completion_tokens=evaluation.completion_tokens,
            ),
        )
        status, verdict, resolution_layer = _complete_or_advance(
            completed_phase=Phase.JUDGE_CHECK,
            keyword_enabled=True,
            cosine_enabled=True,
            judge_enabled=True,
            sanity_check_passed=result.sanity_check_passed or False,
            keyword_verdict=result.keyword_verdict,
            cosine_verdict=result.cosine_verdict,
            judge_verdict=evaluation.verdict,
            force_judge_on_prior_failure=force_judge_on_prior_failure,
        )
        return ResultPatch(
            status=status,
            judge_verdict=evaluation.verdict,
            judge_reasoning=evaluation.reasoning,
            judge_time_ms=evaluation.time_ms,
            judge_completion_tokens=evaluation.completion_tokens,
            verdict=verdict,
            resolution_layer=resolution_layer,
        )

    return _run


def build_inference_unit(  # noqa: PLR0913  # each parameter is a distinct
    # collaborator this worker-thread unit needs (result row, provider registry,
    # timeout budget, clock, bus, cancellation token, and the three per-run grading
    # toggles it must route through on success) — no natural sub-grouping exists
    # that would not obscure the call site
    *,
    result: BenchmarkResult,
    task: BenchmarkTask,
    provider_registry: ProviderRegistry,
    sanity_checker: SanityChecker,
    timeout_ms: DurationMs,
    clock: Clock,
    bus: EventBus,
    token: CancellationToken,
    keyword_enabled: bool,
    cosine_enabled: bool,
    judge_enabled: bool,
) -> Callable[[], ResultPatch]:
    """Build the Phase-2 (inference) unit callable for one result row.

    Fixed `timeout_ms` — no adaptive-timeout consultation (STORY-030).

    Args:
        result: The row's currently persisted state (`PENDING`).
        task: The frozen task supplying the question to send.
        provider_registry: Resolves `result.provider_id` to a live `LLMClient`.
        sanity_checker: The run's constructed deterministic sanity pre-check.
        timeout_ms: The fixed per-attempt call budget.
        clock: The injected time source.
        bus: The application event bus.
        token: The run's live `CancellationToken`.
        keyword_enabled: Whether the keyword phase is enabled for this run.
        cosine_enabled: Whether the cosine phase is enabled for this run.
        judge_enabled: Whether the judge phase is enabled for this run.

    Returns:
        A nullary callable returning the phase's `ResultPatch`, never
        raising `AppError` (contained) or propagating anything but
        `TaskCancelledError`.
    """

    def _run() -> ResultPatch:
        client = provider_registry.get_client(result.provider_id)
        request = ChatRequest(
            model=result.model_name,
            messages=(ChatMessage(role=ChatRole.USER, content=task.question),),
            timeout_ms=timeout_ms,
        )
        started_at = clock.now_utc()
        emit_inference_started(
            bus,
            InferenceStartedEvent(
                run_id=result.run_id,
                result_id=result.result_id,
                task_id=result.task_id,
                provider_id=result.provider_id,
                model_name=result.model_name,
                stage=Phase.INFERENCE.value,
                user_prompt=task.question,
                system_prompt=result.system_prompt_sent,
            ),
        )
        try:
            chat_stream = client.chat_stream(request, token=token)
            response = emit_progress_during(
                chat_stream,
                context=InferenceContext.BENCHMARK_TASK,
                run_id=result.run_id,
                result_id=result.result_id,
                task_id=result.task_id,
                provider_id=result.provider_id,
                model_name=result.model_name,
                clock=clock,
                event_bus=bus,
                token=token,
            )
        except AppError as exc:
            if isinstance(exc, TaskCancelledError):
                raise
            return contain_unit_failure(exc)
        finished_at = clock.now_utc()
        sanitized_response, has_thinking_block = _sanitize_response(response.text)
        sanity_check_passed = sanity_checker.check(response=sanitized_response, task=task)
        completion_tokens = response.completion_tokens
        tokens_estimated = completion_tokens is None
        if completion_tokens is None:
            completion_tokens = math.ceil(len(sanitized_response) / _ESTIMATE_CHARS_PER_TOKEN)
        tokens_per_second = (
            completion_tokens / (response.total_time_ms / _MS_PER_SECOND)
            if response.total_time_ms > 0
            else None
        )
        emit_inference_completed(
            bus,
            InferenceCompletedEvent(
                run_id=result.run_id,
                result_id=result.result_id,
                task_id=result.task_id,
                provider_id=result.provider_id,
                model_name=result.model_name,
                total_time_ms=response.total_time_ms,
                ttft_ms=response.ttft_ms,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=completion_tokens,
                tokens_per_second=tokens_per_second,
            ),
        )
        status, verdict, resolution_layer = _complete_or_advance(
            completed_phase=Phase.INFERENCE,
            keyword_enabled=keyword_enabled,
            cosine_enabled=cosine_enabled,
            judge_enabled=judge_enabled,
            sanity_check_passed=sanity_check_passed,
            keyword_verdict=None,
            cosine_verdict=None,
            judge_verdict=None,
            force_judge_on_prior_failure=False,
        )
        return ResultPatch(
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            user_prompt_sent=task.question,
            raw_response=response.text,
            sanitized_response=sanitized_response,
            has_thinking_block=has_thinking_block,
            response_char_length=len(sanitized_response),
            total_time_ms=response.total_time_ms,
            ttft_ms=response.ttft_ms,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=completion_tokens,
            tokens_per_second=tokens_per_second,
            tokens_estimated=tokens_estimated,
            sanity_check_passed=sanity_check_passed,
            verdict=verdict,
            resolution_layer=resolution_layer,
        )

    return _run
