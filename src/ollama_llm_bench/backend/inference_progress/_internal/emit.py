"""Live inference-progress emission — the shared helper every user-visible LLM call
in the application routes through (04_EVALUATION_PIPELINE.md §6.9).
"""

from datetime import datetime
import math

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import (
    ChatResponse,
    InferenceContext,
    ModelName,
    ProviderId,
    ResultId,
    RunId,
    TaskIdStr,
)
from ollama_llm_bench.backend.events.models import SIGNAL_INFERENCE_PROGRESS, InferenceProgressEvent
from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.provider_registry.protocols import ChatStream

_EMIT_CADENCE_MS = 1000
_ESTIMATE_CHARS_PER_TOKEN = 4


def _emit_progress_during_impl(  # noqa: PLR0913  # mirrors 04_EVALUATION_PIPELINE.md §6.9's
    # shared-helper signature verbatim across all four call sites; grouping into a
    # Struct would break the spec's exact parameter-name contract every caller reuses
    chat_stream: ChatStream,
    *,
    context: InferenceContext,
    run_id: RunId | None,
    result_id: ResultId | None,
    task_id: TaskIdStr | None,
    provider_id: ProviderId,
    model_name: ModelName,
    clock: Clock,
    event_bus: EventBus,
    token: CancellationToken,
) -> ChatResponse:
    """Drain `chat_stream`, emitting a throttled `_inference_progress` heartbeat.

    Runs synchronously on the calling (worker) thread. Emits at >= 1 Hz — once
    per heartbeat/content chunk when >= 1000ms elapsed since the last emission,
    plus immediately on the first content token — and returns the assembled
    `ChatResponse` once the stream is exhausted. Raises whatever the stream
    itself raises (a taxonomy leaf on provider failure, `TaskCancelledError` on
    cancellation) — this helper catches nothing; the caller is responsible for
    containment.

    Args:
        chat_stream: The live `ChatStream` from `LLMClient.chat_stream(...)`.
        context: Which user-visible call surface this is (§7.7a).
        run_id: The owning run, or `None` for a context that has none.
        result_id: The owning result row, or `None` for a context that has none.
        task_id: The owning task, or `None` for a context that has none.
        provider_id: The provider driving this call.
        model_name: The model driving this call.
        clock: The injected time source.
        event_bus: The application event bus.
        token: The run's live `CancellationToken`, checked at every chunk boundary.

    Returns:
        The completed `ChatResponse` once the stream is exhausted.

    Raises:
        AppError: A taxonomy leaf raised by the underlying provider transport.
        TaskCancelledError: `token` observed a cancellation at a chunk boundary.
    """
    start_ms = clock.monotonic_ms()
    last_emit_ms = start_ms
    tokens_received: int | None = None
    first_token_received = False
    accumulator = ""
    token_source = "estimate"  # noqa: S105  # a token-count-source label, not a credential

    def _emit() -> None:
        nonlocal last_emit_ms
        last_emit_ms = clock.monotonic_ms()
        event_bus.emit(
            SIGNAL_INFERENCE_PROGRESS,
            InferenceProgressEvent(
                context=context,
                run_id=run_id,
                result_id=result_id,
                task_id=task_id,
                provider_id=provider_id,
                model_name=model_name,
                elapsed_ms=last_emit_ms - start_ms,
                tokens_received=tokens_received if first_token_received else None,
                first_token_received=first_token_received,
                timestamp_ms=int(datetime.fromisoformat(clock.now_utc()).timestamp() * 1000),
            ),
        )

    for chunk in chat_stream:
        token.raise_if_cancelled()
        if chunk.content and not first_token_received:
            first_token_received = True
            tokens_received = 0
            _emit()
        accumulator += chunk.content
        if chunk.delta_tokens is not None:
            token_source = "delta_tokens"  # noqa: S105  # a token-count-source label
            tokens_received = (tokens_received or 0) + chunk.delta_tokens
        elif token_source == "estimate":  # noqa: S105  # a token-count-source label
            tokens_received = math.ceil(len(accumulator) / _ESTIMATE_CHARS_PER_TOKEN)
        if clock.monotonic_ms() - last_emit_ms >= _EMIT_CADENCE_MS:
            _emit()
    return chat_stream.trailing_response()
