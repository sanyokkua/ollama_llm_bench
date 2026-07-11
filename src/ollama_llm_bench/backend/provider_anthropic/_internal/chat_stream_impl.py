"""The ChatStream implementation: TTFT measurement, usage capture, hard cancellation.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md`` §6.2-6.6, §6.9 (thinking-block concatenation).

Anthropic's raw event stream interleaves several non-content event types
(``message_start``/``content_block_start``/``content_block_delta``/
``content_block_stop``/``message_delta``/``message_stop``/``ping``) between
content-bearing deltas. ``__next__`` therefore loops over raw SDK events
internally, pulling further events until one yields non-empty content or the
stream ends, rather than yielding one ``ChatChunk`` per raw event 1:1.
"""

from collections.abc import Iterator
from dataclasses import dataclass

import anthropic

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import ChatChunk, ChatResponse
from ollama_llm_bench.backend.errors import ErrorContext, HttpTimeoutError, TaskCancelledError
from ollama_llm_bench.backend.infra import Clock
from ollama_llm_bench.backend.provider_anthropic._internal.soft_failure import (
    classify_soft_failure,
)
from ollama_llm_bench.backend.provider_anthropic._internal.translate_exception import (
    translate_chat_exception,
)

__all__: list[str] = ["AnthropicChatStream", "ChatStreamCallInfo"]

_MODEL_ID_TRUNCATE_LEN = 64


@dataclass(frozen=True, slots=True)
class ChatStreamCallInfo:
    """Private, call-scoped bundle of one ``chat_stream`` invocation's identity.

    Never crosses this module's boundary — a strictly internal grouping used
    only to keep ``AnthropicChatStream.__init__``'s argument count within the
    project's parameter-count limit.
    """

    raw_stream: anthropic.Stream[anthropic.types.RawMessageStreamEvent]
    t0: int
    deadline_ms: int
    provider_id: str
    model: str


class AnthropicChatStream:
    """One in-flight chat call's ``ChatStream`` (§6.1's ``ChatStream`` Protocol).

    Constructed already-registered: ``token.add_hard_cancel_hook(raw_stream.close)``
    is called by ``AnthropicClient.chat_stream`` before this object is
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

        Loops over raw SDK events until one carries non-empty content or the
        stream ends — Anthropic's ``ping``/``content_block_start``/
        ``content_block_stop``/``message_stop`` events carry no content and
        are silently skipped after their usage/cancellation/deadline checks.

        Raises:
            TaskCancelledError: The token observed a hard cancellation.
            HttpTimeoutError: The call exceeded its deadline.
            ProviderError: The provider rejected the request or the
                connection failed.
            StopIteration: The stream is exhausted.
        """
        while True:
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
                raw_event = next(self._raw_stream)
            except StopIteration:
                self._finish()
                raise
            except Exception as exc:  # boundary translation catch-all; re-raised as a taxonomy leaf
                self._finish()
                raise translate_chat_exception(exc, context=self._context) from exc
            self._absorb_usage(raw_event)
            content, is_text_block = _extract_content(raw_event)
            if not content:
                continue
            if is_text_block and self._ttft_ms is None:
                self._ttft_ms = self._clock.monotonic_ms() - self._t0
            self._accumulator += content
            return ChatChunk(content=content, delta_tokens=None)

    def trailing_response(self) -> ChatResponse:
        """Return the completed response once the stream is exhausted.

        Returns:
            The assembled ``ChatResponse``, with a soft-failure classification
            in ``error`` when no content was ever received. ``text`` contains
            any ``thinking`` block concatenated before the ``text`` block, in
            document order (§6.9) — this method does not strip it.
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

    def _absorb_usage(self, raw_event: anthropic.types.RawMessageStreamEvent) -> None:
        """Capture token usage from ``message_start``/``message_delta`` events (§6.5).

        Input tokens come from the one ``message_start`` event; output tokens
        come from the final ``message_delta`` event's cumulative count
        (overwritten, not accumulated, since each ``message_delta`` already
        reports the running total).
        """
        if raw_event.type == "message_start":
            self._prompt_tokens = raw_event.message.usage.input_tokens
        elif raw_event.type == "message_delta":
            self._completion_tokens = raw_event.usage.output_tokens

    def _finish(self) -> None:
        """Close the raw stream and remove the hard-cancel hook, exactly once."""
        if not self._finished:
            self._finished = True
            self._raw_stream.close()
            self._token.remove_hard_cancel_hook(self._raw_stream.close)


def _extract_content(raw_event: anthropic.types.RawMessageStreamEvent) -> tuple[str, bool]:
    """Read the content delta off one raw stream event, or ``("", False)`` when absent.

    Returns:
        A ``(content, is_text_block)`` pair. ``is_text_block`` is ``True`` only
        for a ``text_delta`` — this is exactly what gates TTFT (§6.9: "First
        `content_block_delta` of a `text` block"), so a `thinking_delta`
        arriving first never sets ``ttft_ms``. Document-order concatenation
        into ``ChatResponse.text`` (§6.9) falls out for free by appending
        every content-bearing delta as it arrives, since the SDK always
        streams the ``thinking`` block before the ``text`` block when both
        are present.
    """
    if raw_event.type != "content_block_delta":
        return "", False
    delta = raw_event.delta
    if delta.type == "text_delta":
        return delta.text, True
    if delta.type == "thinking_delta":
        return delta.thinking, False
    return "", False
