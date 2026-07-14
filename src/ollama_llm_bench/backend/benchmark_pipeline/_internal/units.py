"""Per-phase-per-task unit callables submitted to the `TaskRunner` (08-B §5.1, §3).

`build_keyword_unit`/`build_cosine_unit` close over their already-constructed
collaborators and return a nullary `Callable[[], ResultPatch]` `run_phase` (the
dispatcher) submits to the `TaskRunner`, blocks on, and persists directly.

`build_inference_attempt`/`build_judge_attempt` instead return an attempt *builder*
— `Callable[[int], Callable[[], T]]` — consumed by
`_internal.stability_dispatch.run_task_with_stability`, which submits one
single-attempt callable per retry attempt and applies the adaptive-timeout/
circuit-breaker/retry-ladder stack around them (STORY-030). Their matching
`finalize_inference_success`/`finalize_judge_success` convert the winning attempt's
raw outcome into the phase's terminal `ResultPatch` (the verdict-combination step),
run once per row on the dispatcher thread after `with_retry` returns.

No unit or attempt callable performs database I/O or emits a run-domain event
(DD-41) — each returns data only; the per-task events this module emits directly
(`_inference_started`/`_inference_completed`, `_judge_started`/`_judge_completed`)
are per-task, not run-domain, events, matching Task 8's existing wrapper set.
`_inference_started`/`_judge_started` fire exactly once per row — at attempt-builder
construction time, not once per retry attempt — matching `08-J_event_bus_catalog.md`'s
"an inference/judge call for one task began" semantics.
"""

from collections.abc import Callable
from dataclasses import dataclass
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
    ModelName,
    ProviderId,
    ResolutionLayer,
    ResultPatch,
    ResultStatus,
    Verdict,
)
from ollama_llm_bench.backend.errors import AppError, TaskCancelledError
from ollama_llm_bench.backend.evaluation import combine_verdict
from ollama_llm_bench.backend.evaluation.models import JudgePhaseOutcome, JudgePhaseResult
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
    "build_inference_attempt",
    "build_judge_attempt",
    "build_judge_timeout_exhausted_patch",
    "build_keyword_unit",
    "finalize_inference_success",
    "finalize_judge_success",
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


def build_judge_attempt(  # noqa: PLR0913  # one parameter per distinct collaborator
    # (the row, the task, the evaluator, the cancellation token, the bus for this
    # unit's own per-task event, the resolved judge stability target) — no natural
    # sub-grouping exists that would not obscure the call site
    *,
    result: BenchmarkResult,
    task: BenchmarkTask,
    evaluator: JudgeEvaluator,
    token: CancellationToken,
    bus: EventBus,
    judge_provider_id: ProviderId,
    judge_model_name: ModelName,
) -> Callable[[int], Callable[[], JudgePhaseResult]]:
    """Build the Phase-5 (judge) per-attempt builder for one result row (STORY-030).

    Emits `_judge_started` exactly once, at construction time — not once per
    retry attempt — using the resolved run-fixed judge target
    (`_internal.judge_target.resolve_judge_target`), never
    `result.provider_id`/`result.model_name` (the row's TEST model, a
    different target).

    Args:
        result: The row's currently persisted state, carrying the keyword
            and cosine phases' verdicts when those phases ran.
        task: The frozen task supplying question/criteria/context.
        evaluator: The run's constructed `JudgeEvaluator`.
        token: The run's live `CancellationToken`, forwarded to the evaluator.
        bus: The application event bus, for the `_judge_started` per-task
            event this builder emits directly.
        judge_provider_id: The run's fixed judge provider (never the row's
            own test-model provider).
        judge_model_name: The run's fixed judge model (never the row's own
            test model).

    Returns:
        A builder taking a `timeout_ms` budget and producing one attempt's
        nullary callable, which returns the evaluator's raw `JudgePhaseResult`
        and raises the evaluator's `AppError` leaves unconverted — classified
        by `_internal.stability_dispatch.run_task_with_stability`, never here.
    """
    emit_judge_started(
        bus,
        JudgeStartedEvent(
            run_id=result.run_id,
            result_id=result.result_id,
            task_id=result.task_id,
            judge_provider_id=judge_provider_id,
            judge_model_name=judge_model_name,
        ),
    )

    def _build_attempt(timeout_ms: DurationMs) -> Callable[[], JudgePhaseResult]:
        def _run_attempt() -> JudgePhaseResult:
            return evaluator.evaluate(
                response=result.sanitized_response or "",
                system_prompt_sent=result.system_prompt_sent,
                task=task,
                timeout_ms=timeout_ms,
                token=token,
            )

        return _run_attempt

    return _build_attempt


def finalize_judge_success(
    *,
    result: BenchmarkResult,
    force_judge_on_prior_failure: bool,
    bus: EventBus,
) -> Callable[[JudgePhaseResult], ResultPatch]:
    """Build the judge phase's winning-attempt finalizer (STORY-030).

    Args:
        result: The row's currently persisted state, carrying the keyword
            and cosine phases' verdicts when those phases ran.
        force_judge_on_prior_failure: The run's force-judge setting.
        bus: The application event bus, for the `_judge_completed` per-task
            event this finalizer emits on a resolved outcome.

    Returns:
        A closure converting the winning attempt's raw `JudgePhaseResult`
        into the phase's terminal `ResultPatch` — the verdict-combination
        step, unchanged in substance from the pre-STORY-030 single-attempt
        `build_judge_unit`.
    """

    def _finalize(evaluation: JudgePhaseResult) -> ResultPatch:
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

    return _finalize


def build_judge_timeout_exhausted_patch() -> Callable[[], ResultPatch]:
    """Build the judge phase's per-task timeout-ladder-exhaustion terminal patch.

    Used as `_internal.stability_dispatch.run_task_with_stability`'s
    `on_timeout_exhausted` argument for the JUDGE_CHECK phase only — the one
    place role=JUDGE genuinely diverges from role=INFERENCE's generic
    `contain_unit_failure` mapping (`04_EVALUATION_PIPELINE.md` §6.5 item 1,
    §8; STORY-030-AC-3). Also used, unchanged, as the pre-attempt fast path
    when the judge target is already excluded (STORY-030-AC-4).

    Returns:
        A nullary callable returning the `FAILED_JUDGE_TIMEOUT` terminal
        `ResultPatch`; the combination step is explicitly NOT applied —
        `verdict`/`resolution_layer` stay unset (`None`), matching every
        other terminal-failure `ResultPatch` in this module.
    """

    def _build() -> ResultPatch:
        return ResultPatch(
            status=ResultStatus.FAILED_JUDGE_TIMEOUT,
            error_kind=ErrorKind.JUDGE_TIMEOUT,
            error_message="Judge call exhausted adaptive budget for this task.",
        )

    return _build


@dataclass(slots=True, frozen=True)
class _InferenceAttemptOutcome:
    """One successful inference attempt's raw data (`_internal`-only, never crosses
    this module's boundary — see `coding-style.md`'s dataclass exemption)."""

    response_text: str
    total_time_ms: DurationMs
    ttft_ms: DurationMs | None
    prompt_tokens: int | None
    completion_tokens: int
    tokens_estimated: bool
    tokens_per_second: float | None
    sanitized_response: str
    has_thinking_block: bool
    sanity_check_passed: bool
    started_at: str
    finished_at: str


def build_inference_attempt(  # noqa: PLR0913  # each parameter is a distinct
    # collaborator this attempt builder needs (result row, provider registry,
    # sanity checker, clock, bus, cancellation token) — no natural sub-grouping
    # exists that would not obscure the call site
    *,
    result: BenchmarkResult,
    task: BenchmarkTask,
    provider_registry: ProviderRegistry,
    sanity_checker: SanityChecker,
    clock: Clock,
    bus: EventBus,
    token: CancellationToken,
) -> Callable[[int], Callable[[], _InferenceAttemptOutcome]]:
    """Build the Phase-2 (inference) per-attempt builder for one result row (STORY-030).

    Emits `_inference_started` exactly once, at construction time — not once
    per retry attempt.

    Args:
        result: The row's currently persisted state (`PENDING`).
        task: The frozen task supplying the question to send.
        provider_registry: Resolves `result.provider_id` to a live `LLMClient`.
        sanity_checker: The run's constructed deterministic sanity pre-check.
        clock: The injected time source.
        bus: The application event bus, for the `_inference_started` per-task
            event this builder emits directly.
        token: The run's live `CancellationToken`.

    Returns:
        A builder taking a `timeout_ms` budget and producing one attempt's
        nullary callable, which returns `_InferenceAttemptOutcome` on success
        and raises the client's `AppError` leaves unconverted — classified by
        `_internal.stability_dispatch.run_task_with_stability`, never here.
    """
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

    def _build_attempt(timeout_ms: DurationMs) -> Callable[[], _InferenceAttemptOutcome]:
        def _run_attempt() -> _InferenceAttemptOutcome:
            request = ChatRequest(
                model=result.model_name,
                messages=(ChatMessage(role=ChatRole.USER, content=task.question),),
                timeout_ms=timeout_ms,
            )
            started_at = clock.now_utc()
            client = provider_registry.get_client(result.provider_id)
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
            return _InferenceAttemptOutcome(
                response_text=response.text,
                total_time_ms=response.total_time_ms,
                ttft_ms=response.ttft_ms,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=completion_tokens,
                tokens_estimated=tokens_estimated,
                tokens_per_second=tokens_per_second,
                sanitized_response=sanitized_response,
                has_thinking_block=has_thinking_block,
                sanity_check_passed=sanity_check_passed,
                started_at=started_at,
                finished_at=finished_at,
            )

        return _run_attempt

    return _build_attempt


def finalize_inference_success(  # noqa: PLR0913  # each parameter is a distinct
    # input the winning-attempt combination step needs (the row, the task supplying
    # the sent prompt, the bus, and the three per-run grading toggles) — no natural
    # sub-grouping exists that would not obscure the call site
    *,
    result: BenchmarkResult,
    task: BenchmarkTask,
    bus: EventBus,
    keyword_enabled: bool,
    cosine_enabled: bool,
    judge_enabled: bool,
) -> Callable[[_InferenceAttemptOutcome], ResultPatch]:
    """Build the inference phase's winning-attempt finalizer (STORY-030).

    Args:
        result: The row's currently persisted state (`PENDING`).
        task: The frozen task supplying the question that was sent.
        bus: The application event bus, for the `_inference_completed`
            per-task event this finalizer emits.
        keyword_enabled: Whether the keyword phase is enabled for this run.
        cosine_enabled: Whether the cosine phase is enabled for this run.
        judge_enabled: Whether the judge phase is enabled for this run.

    Returns:
        A closure converting the winning attempt's raw
        `_InferenceAttemptOutcome` into the phase's terminal `ResultPatch` —
        unchanged in substance from the pre-STORY-030 single-attempt
        `build_inference_unit`.
    """

    def _finalize(outcome: _InferenceAttemptOutcome) -> ResultPatch:
        emit_inference_completed(
            bus,
            InferenceCompletedEvent(
                run_id=result.run_id,
                result_id=result.result_id,
                task_id=result.task_id,
                provider_id=result.provider_id,
                model_name=result.model_name,
                total_time_ms=outcome.total_time_ms,
                ttft_ms=outcome.ttft_ms,
                prompt_tokens=outcome.prompt_tokens,
                completion_tokens=outcome.completion_tokens,
                tokens_per_second=outcome.tokens_per_second,
            ),
        )
        status, verdict, resolution_layer = _complete_or_advance(
            completed_phase=Phase.INFERENCE,
            keyword_enabled=keyword_enabled,
            cosine_enabled=cosine_enabled,
            judge_enabled=judge_enabled,
            sanity_check_passed=outcome.sanity_check_passed,
            keyword_verdict=None,
            cosine_verdict=None,
            judge_verdict=None,
            force_judge_on_prior_failure=False,
        )
        return ResultPatch(
            status=status,
            started_at=outcome.started_at,
            finished_at=outcome.finished_at,
            user_prompt_sent=task.question,
            raw_response=outcome.response_text,
            sanitized_response=outcome.sanitized_response,
            has_thinking_block=outcome.has_thinking_block,
            response_char_length=len(outcome.sanitized_response),
            total_time_ms=outcome.total_time_ms,
            ttft_ms=outcome.ttft_ms,
            prompt_tokens=outcome.prompt_tokens,
            completion_tokens=outcome.completion_tokens,
            tokens_per_second=outcome.tokens_per_second,
            tokens_estimated=outcome.tokens_estimated,
            sanity_check_passed=outcome.sanity_check_passed,
            verdict=verdict,
            resolution_layer=resolution_layer,
        )

    return _finalize
