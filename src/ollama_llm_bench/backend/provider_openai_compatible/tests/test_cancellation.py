"""Tests proving STORY-018-AC-6: mid-stream hard cancellation aborts promptly,
closes the stream, and raises ``TaskCancelledError`` within
``provider.hard_cancel_max_ms``.

Source of truth: ``docs/stories/story-018-openai-compatible-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md`` §6.6.

Unit-tier (per the story's Test Plan): a fake stream driven by a real
``CancellationToken`` — no network. This isolates the cancellation contract
(``OpenAICompatibleChatStream.__next__``'s hard-cancel poll and the registered
abort hook) from transport concerns, which the wire-stub tests elsewhere in this
package already cover.
"""

import time

import openai
import pytest

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import CancelReason
from ollama_llm_bench.backend.errors import TaskCancelledError
from ollama_llm_bench.backend.provider_openai_compatible._internal.chat_stream_impl import (
    ChatStreamCallInfo,
    OpenAICompatibleChatStream,
)
from ollama_llm_bench.backend.provider_openai_compatible.tests.conftest import FakeClock

_HARD_CANCEL_MAX_MS = 2000


class _FakeRawStream:
    """Strictly private, colocated-test-only double for the raw ``openai.Stream``
    iterator ``OpenAICompatibleChatStream`` wraps.

    Yields canned chunk-shaped objects on ``__next__``; records whether
    ``close()`` was called so the test can assert no orphaned connection is
    left behind.
    """

    def __init__(self, *, chunks: list[object]) -> None:
        self._chunks = chunks
        self._index = 0
        self.closed = False

    def __iter__(self) -> "_FakeRawStream":
        return self

    def __next__(self) -> object:
        if self._index >= len(self._chunks):
            raise StopIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk

    def close(self) -> None:
        self.closed = True


def _make_chunk(content: str) -> openai.types.chat.ChatCompletionChunk:
    return openai.types.chat.ChatCompletionChunk.model_construct(
        id="1",
        object="chat.completion.chunk",
        created=0,
        model="test-model",
        choices=[
            openai.types.chat.chat_completion_chunk.Choice.model_construct(
                index=0,
                delta=openai.types.chat.chat_completion_chunk.ChoiceDelta.model_construct(
                    content=content
                ),
                finish_reason=None,
            )
        ],
        usage=None,
    )


def test_hard_cancel_aborts_stream_within_bound(fake_clock: FakeClock) -> None:
    """Proves: STORY-018-AC-6

    Given a ``chat`` call in flight and the run's ``CancellationToken`` is
    hard-cancelled after the second chunk, when the cancellation fires, then
    the client stops consuming at the next chunk boundary, closes the
    stream, and raises ``TaskCancelledError`` promptly (well within
    ``provider.hard_cancel_max_ms``), leaving no orphaned streaming
    connection.
    """
    # Arrange
    raw_stream = _FakeRawStream(
        chunks=[_make_chunk("first"), _make_chunk("second"), _make_chunk("third")]
    )
    call = ChatStreamCallInfo(
        raw_stream=raw_stream,  # type: ignore[arg-type]  # structural double; real type is openai.Stream
        t0=fake_clock.monotonic_ms(),
        deadline_ms=fake_clock.monotonic_ms() + 60_000,
        provider_id="11111111-1111-4111-8111-111111111111",
        model="test-model",
    )
    token = CancellationToken(clock=fake_clock)
    stream = OpenAICompatibleChatStream(call=call, clock=fake_clock, token=token)
    token.add_hard_cancel_hook(raw_stream.close)

    # Act: consume two chunks, then hard-cancel before the third.
    next(stream)
    next(stream)
    started_wall = time.monotonic()
    token.cancel(reason=CancelReason.USER_STOP, hard=True)

    # Assert
    with pytest.raises(TaskCancelledError):
        next(stream)
    elapsed_ms = (time.monotonic() - started_wall) * 1000
    assert elapsed_ms < _HARD_CANCEL_MAX_MS
    assert raw_stream.closed is True


def test_hard_cancel_hook_closes_stream_even_when_not_polled_first(fake_clock: FakeClock) -> None:
    """Proves: STORY-018-AC-6

    Given the token is already hard-cancelled before ``add_hard_cancel_hook``
    is called (a cancel raced ahead of the client's own registration), then
    the hook still fires immediately, closing the raw stream — the abort
    hook, not just the chunk-boundary poll, is the mechanism that guarantees
    no orphaned connection survives a hard cancel.
    """
    # Arrange
    raw_stream = _FakeRawStream(chunks=[_make_chunk("first")])
    token = CancellationToken(clock=fake_clock)
    token.cancel(reason=CancelReason.APP_SHUTDOWN, hard=True)

    # Act
    token.add_hard_cancel_hook(raw_stream.close)

    # Assert
    assert raw_stream.closed is True
