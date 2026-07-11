"""Tests proving STORY-020-AC-5: mid-stream hard cancellation aborts promptly,
closes the stream, and raises ``TaskCancelledError`` within
``provider.hard_cancel_max_ms``.

Source of truth: ``docs/stories/story-020-gemini-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md``
§6.6.

Unit-tier (per the story's Test Plan): a fake raw stream driven by a real
``CancellationToken`` — no network. This isolates the cancellation contract
(``GeminiChatStream.__next__``'s hard-cancel poll and the registered abort
hook) from transport concerns, which the wire-stub tests elsewhere in this
package already cover.
"""

import time

import pytest

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import CancelReason
from ollama_llm_bench.backend.errors import TaskCancelledError
from ollama_llm_bench.backend.provider_gemini._internal.chat_stream_impl import (
    ChatStreamCallInfo,
    GeminiChatStream,
)
from ollama_llm_bench.backend.provider_gemini.tests.conftest import FakeClock

_HARD_CANCEL_MAX_MS = 2000


class _FakePart:
    """Strictly private, colocated-test-only double for ``types.Part``.

    Only the ``text`` attribute the production code reads is modelled.
    """

    def __init__(self, *, text: str) -> None:
        self.text = text


class _FakeContent:
    def __init__(self, *, parts: list[_FakePart]) -> None:
        self.parts = parts


class _FakeCandidate:
    def __init__(self, *, content: _FakeContent) -> None:
        self.content = content


class _FakeChunk:
    """Strictly private, colocated-test-only double for
    ``types.GenerateContentResponse``. Only the ``candidates``/
    ``usage_metadata`` shape the production code reads is modelled."""

    def __init__(self, *, text: str) -> None:
        self.candidates = [_FakeCandidate(content=_FakeContent(parts=[_FakePart(text=text)]))]
        self.usage_metadata = None


class _FakeRawStream:
    """Strictly private, colocated-test-only double for the
    ``Iterator[GenerateContentResponse]`` ``GeminiChatStream`` wraps.

    Yields canned chunk-shaped objects on ``__next__``; records whether
    ``close()`` was called so the test can assert no orphaned connection is
    left behind.
    """

    def __init__(self, *, chunks: list[_FakeChunk]) -> None:
        self._chunks = chunks
        self._index = 0
        self.closed = False

    def __iter__(self) -> "_FakeRawStream":
        return self

    def __next__(self) -> _FakeChunk:
        if self._index >= len(self._chunks):
            raise StopIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk

    def close(self) -> None:
        self.closed = True


def test_hard_cancel_aborts_stream_within_bound(fake_clock: FakeClock) -> None:
    """Proves: STORY-020-AC-5

    Given a ``chat`` call in flight and the run's ``CancellationToken`` is
    hard-cancelled after the second chunk, when the cancellation fires, then
    the client stops consuming at the next chunk boundary, closes the
    stream, and raises ``TaskCancelledError`` promptly (well within
    ``provider.hard_cancel_max_ms``), leaving no orphaned streaming
    connection.
    """
    # Arrange
    raw_stream = _FakeRawStream(
        chunks=[_FakeChunk(text="first"), _FakeChunk(text="second"), _FakeChunk(text="third")]
    )
    call = ChatStreamCallInfo(
        raw_stream=raw_stream,  # type: ignore[arg-type]  # structural double; real type is Iterator[GenerateContentResponse]
        t0=fake_clock.monotonic_ms(),
        deadline_ms=fake_clock.monotonic_ms() + 60_000,
        provider_id="33333333-3333-4333-8333-333333333333",
        model="gemini-test-model",
    )
    token = CancellationToken(clock=fake_clock)
    stream = GeminiChatStream(call=call, clock=fake_clock, token=token)
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
    """Proves: STORY-020-AC-5

    Given the token is already hard-cancelled before
    ``add_hard_cancel_hook`` is called (a cancel raced ahead of the client's
    own registration), then the hook still fires immediately, closing the
    raw stream — the abort hook, not just the chunk-boundary poll, is the
    mechanism that guarantees no orphaned connection survives a hard cancel.
    """
    # Arrange
    raw_stream = _FakeRawStream(chunks=[_FakeChunk(text="first")])
    token = CancellationToken(clock=fake_clock)
    token.cancel(reason=CancelReason.APP_SHUTDOWN, hard=True)

    # Act
    token.add_hard_cancel_hook(raw_stream.close)

    # Assert
    assert raw_stream.closed is True
