"""The judge-phase evaluator: the call, and the parse/retry loop (§7-§10 of
08-P_judge_protocol.md)."""

import structlog

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import (
    BenchmarkTask,
    ChatRequest,
    DurationMs,
    ModelNameStr,
    NonNegativeInt,
    ResponseFormat,
)
from ollama_llm_bench.backend.errors import AppError, ProviderContextLengthError
from ollama_llm_bench.backend.evaluation._internal.judge.parsing import parse_judge_response
from ollama_llm_bench.backend.evaluation._internal.judge.prompt import build_judge_messages
from ollama_llm_bench.backend.evaluation._internal.parameters import _EvaluationParameters
from ollama_llm_bench.backend.evaluation.models import JudgePhaseOutcome, JudgePhaseResult
from ollama_llm_bench.backend.provider_registry import LLMClient

log = structlog.get_logger()

_JUDGE_TEMPERATURE = 0.0
_BUDGET_EXHAUSTED_MESSAGE = (
    "The judge model exhausted its completion-token budget before emitting a "
    "verdict; raise eval.judge_max_completion_tokens or choose a non-reasoning "
    "judge model."
)


class _JudgeEvaluatorImpl:
    """The concrete judge-phase evaluator; never constructed outside ``api.py``."""

    def __init__(
        self, *, llm_client: LLMClient, model_name: ModelNameStr, parameters: _EvaluationParameters
    ) -> None:
        self._llm_client = llm_client
        self._model_name = model_name
        self._parameters = parameters

    def evaluate(
        self,
        *,
        response: str,
        system_prompt_sent: str | None,
        task: BenchmarkTask,
        timeout_ms: DurationMs,
        token: CancellationToken,
    ) -> JudgePhaseResult:
        """Issue one judge call (with retries) grading ``response`` against ``task``.

        Args:
            response: The candidate ``sanitized_response`` text.
            system_prompt_sent: The system prompt the candidate model
                received for this result, or ``None``.
            task: The frozen task providing question/criteria/context.
            timeout_ms: The per-attempt call budget.
            token: The run's live ``CancellationToken``, forwarded verbatim
                to the underlying ``LLMClient.chat`` call.

        Returns:
            The judge phase's outcome, never with a numeric score.

        Raises:
            ProviderContextLengthError: The assembled prompt exceeded the
                judge model's context window (DD-46 §4.3) — a permanent,
                non-retried error surfaced uncaught to the caller.
        """
        total_time_ms = 0
        last_completion_tokens: NonNegativeInt | None = None
        last_truncated = False
        max_attempts = self._parameters.judge_max_parse_retries + 1

        for attempt in range(max_attempts):
            request = self._build_request(
                task=task,
                sanitized_response=response,
                system_prompt_sent=system_prompt_sent,
                timeout_ms=timeout_ms,
                is_retry=attempt > 0,
            )
            try:
                chat_response = self._llm_client.chat(request, token=token)
            except ProviderContextLengthError:
                raise
            except AppError as exc:
                log.warning("judge_call_failed", attempt=attempt + 1, error=str(exc))
                return JudgePhaseResult(
                    outcome=JudgePhaseOutcome.TRANSPORT_FAILURE,
                    verdict=None,
                    reasoning=f"Judge call failed: {exc}",
                    time_ms=total_time_ms,
                    completion_tokens=last_completion_tokens,
                )

            total_time_ms += chat_response.total_time_ms
            last_completion_tokens = chat_response.completion_tokens
            last_truncated = self._is_truncated(chat_response.completion_tokens)
            parsed = parse_judge_response(chat_response.text)
            if parsed is not None:
                return JudgePhaseResult(
                    outcome=JudgePhaseOutcome.RESOLVED,
                    verdict=parsed.verdict,
                    reasoning=parsed.reasoning,
                    time_ms=total_time_ms,
                    completion_tokens=last_completion_tokens,
                )

        return self._exhausted_result(
            attempts=max_attempts,
            truncated=last_truncated,
            total_time_ms=total_time_ms,
            completion_tokens=last_completion_tokens,
        )

    def _build_request(
        self,
        *,
        task: BenchmarkTask,
        sanitized_response: str,
        system_prompt_sent: str | None,
        timeout_ms: DurationMs,
        is_retry: bool,
    ) -> ChatRequest:
        messages = build_judge_messages(
            task=task,
            sanitized_response=sanitized_response,
            system_prompt_sent=system_prompt_sent,
            is_retry=is_retry,
        )
        return ChatRequest(
            model=self._model_name,
            messages=messages,
            timeout_ms=timeout_ms,
            temperature=_JUDGE_TEMPERATURE,
            max_output_tokens=self._parameters.judge_max_completion_tokens,
            response_format=ResponseFormat.JSON,
        )

    def _is_truncated(self, completion_tokens: NonNegativeInt | None) -> bool:
        return (
            completion_tokens is not None
            and completion_tokens >= self._parameters.judge_max_completion_tokens
        )

    def _exhausted_result(
        self,
        *,
        attempts: int,
        truncated: bool,
        total_time_ms: DurationMs,
        completion_tokens: NonNegativeInt | None,
    ) -> JudgePhaseResult:
        if truncated:
            diagnostic = _BUDGET_EXHAUSTED_MESSAGE
        else:
            diagnostic = f"Judge returned an unparseable response after {attempts} attempts."
        log.warning("judge_parse_exhausted", attempts=attempts, truncated=truncated)
        return JudgePhaseResult(
            outcome=JudgePhaseOutcome.PARSE_EXHAUSTED,
            verdict=None,
            reasoning=diagnostic,
            time_ms=total_time_ms,
            completion_tokens=completion_tokens,
        )
