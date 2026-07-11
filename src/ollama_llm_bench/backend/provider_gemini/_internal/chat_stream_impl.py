"""The ChatStream implementation: TTFT measurement, usage capture, hard cancellation.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md`` §6.2-6.6, §6.9 (reasoning-part concatenation),
§6.5a (per-chunk ``delta_tokens``).

Gemini's raw stream is an ``Iterator[types.GenerateContentResponse]`` — one
response object per streamed chunk, each carrying its own
``candidates[0].content.parts`` and (per §6.5a) its own ``usage_metadata``.
Unlike Anthropic's typed multi-event-per-content-block stream, there is no
separate non-content event type to skip: every yielded
``GenerateContentResponse`` either carries >=1 part (possibly a reasoning
part, possibly a text part, possibly both) or carries none (a heartbeat-only
chunk), so ``__next__`` loops until a chunk yields non-empty content or the
stream ends, exactly mirroring the Anthropic wrapper's shape.

``GenerateContentResponse.text`` (the SDK's own convenience property) is
deliberately NOT used here — it silently excludes any part where
``part.thought is True``, which would strip exactly the reasoning content
STORY-020-AC-3 requires kept, concatenated in document order, in
``ChatResponse.text``.
"""

from collections.abc import Iterator
from dataclasses import dataclass

from google.genai import types as genai_types

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import ChatChunk, ChatResponse
from ollama_llm_bench.backend.errors import ErrorContext, HttpTimeoutError, TaskCancelledError
from ollama_llm_bench.backend.infra import Clock
from ollama_llm_bench.backend.provider_gemini._internal.soft_failure import classify_soft_failure
from ollama_llm_bench.backend.provider_gemini._internal.translate_exception import (
    translate_chat_exception,
)

__all__: list[str] = ["ChatStreamCallInfo", "GeminiChatStream"]

_MODEL_ID_TRUNCATE_LEN = 64


@dataclass(frozen=True, slots=True)
class ChatStreamCallInfo:
    """Private, call-scoped bundle of one ``chat_stream`` invocation's identity.

    Never crosses this module's boundary — a strictly internal grouping used
    only to keep ``GeminiChatStream.__init__``'s argument count within the
    project's parameter-count limit.
    """

    raw_stream: Iterator[genai_types.GenerateContentResponse]
    t0: int
    deadline_ms: int
    provider_id: str
    model: str


class GeminiChatStream:
    """One in-flight chat call's ``ChatStream`` (§6.1's ``ChatStream`` Protocol).

    Constructed already-registered: ``token.add_hard_cancel_hook(raw_stream.close)``
    is called by ``GeminiClient.chat_stream`` before this object is
    returned, and this class removes it exactly once, in ``_finish()``, on
    every exit path (natural exhaustion, deadline, cancellation, or an SDK
    exception).
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

        Loops over raw ``GenerateContentResponse`` objects until one carries
        non-empty content or the stream ends — a chunk with no parts at all
        (a heartbeat) is silently skipped after its usage/cancellation/
        deadline checks, exactly mirroring the Anthropic wrapper's shape.

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
                raw_chunk = next(self._raw_stream)
            except StopIteration:
                self._finish()
                raise
            except Exception as exc:  # boundary translation catch-all; re-raised as a taxonomy leaf
                self._finish()
                raise translate_chat_exception(exc, context=self._context) from exc
            delta_tokens = _extract_delta_tokens(raw_chunk)
            self._absorb_usage(raw_chunk)
            content = _extract_content(raw_chunk)
            if not content:
                continue
            if self._ttft_ms is None:
                self._ttft_ms = self._clock.monotonic_ms() - self._t0
            self._accumulator += content
            return ChatChunk(content=content, delta_tokens=delta_tokens)

    def trailing_response(self) -> ChatResponse:
        """Return the completed response once the stream is exhausted.

        Returns:
            The assembled ``ChatResponse``, with a soft-failure
            classification in ``error`` when no content was ever received.
            ``text`` contains any reasoning part concatenated before the
            text part, in document order (§6.9) — this method does not
            strip it.
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

    def _absorb_usage(self, raw_chunk: genai_types.GenerateContentResponse) -> None:
        """Capture the final token usage from ``usage_metadata`` (§6.5).

        Overwritten (not accumulated) on every chunk that carries it: Gemini
        attaches ``usage_metadata`` to the final streamed response object
        (§6.5), so the last non-``None`` value observed wins.
        """
        usage = raw_chunk.usage_metadata
        if usage is None:
            return
        if usage.prompt_token_count is not None:
            self._prompt_tokens = usage.prompt_token_count
        if usage.candidates_token_count is not None:
            self._completion_tokens = usage.candidates_token_count

    def _finish(self) -> None:
        """Close the raw stream and remove the hard-cancel hook, exactly once."""
        if not self._finished:
            self._finished = True
            self._raw_stream.close()  # type: ignore[attr-defined]  # Iterator[...] is a real generator; .close() is the language-level generator protocol, not an SDK-declared method
            self._token.remove_hard_cancel_hook(self._raw_stream.close)  # type: ignore[attr-defined]


def _extract_content(raw_chunk: genai_types.GenerateContentResponse) -> str:
    """Concatenate every part's text in document order, reasoning included (§6.9).

    Deliberately does not use ``GenerateContentResponse.text`` — that
    convenience property silently excludes any part where ``part.thought is
    True``, which would strip exactly the reasoning content STORY-020-AC-3
    requires kept.

    Returns:
        The concatenation of every non-``None`` ``Part.text`` on the first
        candidate, in document order; ``""`` when the chunk carries no
        content-bearing parts (a heartbeat chunk).
    """
    if not raw_chunk.candidates:
        return ""
    content = raw_chunk.candidates[0].content
    if content is None or not content.parts:
        return ""
    return "".join(part.text for part in content.parts if part.text)


def _extract_delta_tokens(raw_chunk: genai_types.GenerateContentResponse) -> int | None:
    """Read this chunk's own ``usage_metadata.candidates_token_count`` (§6.5a).

    Gemini streaming responses typically carry usage metadata on each
    streamed chunk; when present, the client maps that count directly onto
    the yielded ``ChatChunk.delta_tokens`` (§6.5a) — no diffing against a
    running total, per the spec's own framing of this field.

    Returns:
        The chunk's own ``candidates_token_count``, or ``None`` when this
        chunk carries no usage metadata or no candidate token count.
    """
    usage = raw_chunk.usage_metadata
    if usage is None:
        return None
    return usage.candidates_token_count
