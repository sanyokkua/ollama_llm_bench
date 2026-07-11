"""The ChatStream implementation: TTFT measurement, usage capture, hard cancellation.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md`` §6.2-6.6.
"""

from collections.abc import Iterator
from dataclasses import dataclass

import openai

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import ChatChunk, ChatResponse
from ollama_llm_bench.backend.errors import ErrorContext, HttpTimeoutError, TaskCancelledError
from ollama_llm_bench.backend.infra import Clock
from ollama_llm_bench.backend.provider_openai_compatible._internal.soft_failure import (
    classify_soft_failure,
)
from ollama_llm_bench.backend.provider_openai_compatible._internal.translate_exception import (
    translate_chat_exception,
)

__all__: list[str] = ["ChatStreamCallInfo", "OpenAICompatibleChatStream"]

_MODEL_ID_TRUNCATE_LEN = 64


@dataclass(frozen=True, slots=True)
class ChatStreamCallInfo:
    """Private, call-scoped bundle of one ``chat_stream`` invocation's identity.

    Never crosses this module's boundary — a strictly internal grouping used
    only to keep ``OpenAICompatibleChatStream.__init__``'s argument count
    within the project's parameter-count limit.
    """

    raw_stream: openai.Stream[openai.types.chat.ChatCompletionChunk]
    t0: int
    deadline_ms: int
    provider_id: str
    model: str


class OpenAICompatibleChatStream:
    """One in-flight chat call's ``ChatStream`` (§6.1's ``ChatStream`` Protocol).

    Constructed already-registered: ``token.add_hard_cancel_hook(raw_stream.close)``
    is called by ``OpenAICompatibleClient.chat_stream`` before this object is
    returned, and this class removes it exactly once, in ``_finish()``, on every
    exit path (natural exhaustion, deadline, cancellation, or an SDK exception).
    """

    def __init__(self, *, call: ChatStreamCallInfo, clock: Clock, token: CancellationToken) -> None:
        """Construct the stream wrapper around one already-open raw SDK stream.

        Args:
            call: The call-scoped identity (raw stream, timing, and error
                context fields) for this one invocation.
            clock: The injected time source for TTFT/deadline measurement.
            token: The run's live cancellation token; polled at chunk
                boundaries and already holding this stream's abort hook.
        """
        self._raw_stream = call.raw_stream
        self._clock = clock
        self._t0 = call.t0
        self._deadline_ms = call.deadline_ms
        self._token = token
        self._context = ErrorContext(
            provider_id=call.provider_id,
            model_id_truncated=call.model[:_MODEL_ID_TRUNCATE_LEN],
        )
        self._accumulator = ""
        self._ttft_ms: int | None = None
        self._prompt_tokens: int | None = None
        self._completion_tokens: int | None = None
        self._finished = False

    def __iter__(self) -> Iterator[ChatChunk]:
        """Return the chunk iterator itself."""
        return self

    def __next__(self) -> ChatChunk:
        """Return the next content chunk, translating any failure at the boundary.

        Raises:
            TaskCancelledError: The token observed a hard cancellation.
            HttpTimeoutError: The call exceeded its deadline.
            ProviderError: The provider rejected the request or the
                connection failed.
            StopIteration: The stream is exhausted.
        """
        if self._token.is_hard_cancelled:
            self._finish()
            raise TaskCancelledError(message="hard-cancelled", context=self._context)
        if self._clock.monotonic_ms() > self._deadline_ms:
            self._finish()
            elapsed = self._clock.monotonic_ms() - self._t0
            raise HttpTimeoutError(
                message=f"deadline exceeded after {elapsed}ms", context=self._context
            )
        try:
            raw_chunk = next(self._raw_stream)
        except StopIteration:
            self._finish()
            raise
        except Exception as exc:  # boundary translation catch-all; re-raised as a taxonomy leaf
            self._finish()
            raise translate_chat_exception(exc, context=self._context) from exc
        content = _extract_content(raw_chunk)
        if content and self._ttft_ms is None:
            self._ttft_ms = self._clock.monotonic_ms() - self._t0
        self._accumulator += content
        self._merge_usage(raw_chunk)
        return ChatChunk(content=content, delta_tokens=None)

    def trailing_response(self) -> ChatResponse:
        """Return the completed response once the stream is exhausted.

        Returns:
            The assembled ``ChatResponse``, with a soft-failure classification
            in ``error`` when no content was ever received.
        """
        return ChatResponse(
            text=self._accumulator,
            total_time_ms=self._clock.monotonic_ms() - self._t0,
            streamed=True,
            ttft_ms=self._ttft_ms,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
            error=classify_soft_failure(self._accumulator),
        )

    def _merge_usage(self, raw_chunk: openai.types.chat.ChatCompletionChunk) -> None:
        """Capture token usage from a chunk, when the provider reports it."""
        usage = raw_chunk.usage
        if usage is not None:
            self._prompt_tokens = usage.prompt_tokens
            self._completion_tokens = usage.completion_tokens

    def _finish(self) -> None:
        """Close the raw stream and remove the hard-cancel hook, exactly once."""
        if not self._finished:
            self._finished = True
            self._raw_stream.close()
            self._token.remove_hard_cancel_hook(self._raw_stream.close)


def _extract_content(raw_chunk: openai.types.chat.ChatCompletionChunk) -> str:
    """Read the content delta off one streamed chunk, or ``""`` when absent."""
    if not raw_chunk.choices:
        return ""
    content = raw_chunk.choices[0].delta.content
    return content or ""
