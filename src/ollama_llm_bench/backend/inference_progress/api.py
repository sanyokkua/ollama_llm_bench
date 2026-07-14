"""Public factory-free entry point for the shared inference-progress helper (§6.9)."""

import icontract

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
from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.inference_progress._internal.emit import (
    _emit_progress_during_impl,
)
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.provider_registry.protocols import ChatStream

__all__: list[str] = ["emit_progress_during"]


@icontract.require(
    lambda context, run_id: context == InferenceContext.PROVIDER_TEST or run_id is not None,
    "run_id must be set for every InferenceContext except PROVIDER_TEST — every caller in "
    "this codebase already knows its run_id before starting a tracked call",
)
def emit_progress_during(  # noqa: PLR0913  # mirrors §6.9's shared-helper signature verbatim
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

    Args:
        chat_stream: The live `ChatStream` from `LLMClient.chat_stream(...)`.
        context: Which user-visible call surface this is (§7.7a).
        run_id: The owning run, or `None` only for `PROVIDER_TEST`.
        result_id: The owning result row, or `None` for a context without one.
        task_id: The owning task, or `None` for a context without one.
        provider_id: The provider driving this call.
        model_name: The model driving this call.
        clock: The injected time source.
        event_bus: The application event bus.
        token: The caller's `CancellationToken`, checked at every chunk boundary.

    Returns:
        The completed `ChatResponse` once the stream is exhausted.

    Raises:
        AppError: A taxonomy leaf raised by the underlying provider transport.
        TaskCancelledError: `token` observed a cancellation at a chunk boundary.
    """
    return _emit_progress_during_impl(
        chat_stream,
        context=context,
        run_id=run_id,
        result_id=result_id,
        task_id=task_id,
        provider_id=provider_id,
        model_name=model_name,
        clock=clock,
        event_bus=event_bus,
        token=token,
    )
