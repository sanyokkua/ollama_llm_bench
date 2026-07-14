"""Proves: STORY-030 (moved from benchmark_pipeline, unchanged) / STORY-035 (Task 2)

Unit tests for the shared `emit_progress_during` helper (04_EVALUATION_PIPELINE.md
§6.9), now living in `backend/inference_progress/` so every user-visible
LLM-progress caller reuses one implementation.
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import (
    CancelReason,
    ChatChunk,
    ChatResponse,
    InferenceContext,
    Iso8601Utc,
)
from ollama_llm_bench.backend.errors import HttpConnectionError, TaskCancelledError
from ollama_llm_bench.backend.events.models import InferenceProgressEvent
from ollama_llm_bench.backend.events.protocols import Subscription
from ollama_llm_bench.backend.inference_progress import emit_progress_during
from ollama_llm_bench.backend.infra.protocols import Clock

_RUN_ID = 1
_RESULT_ID = 1
_TASK_ID = "task-1"
_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME = "llama3"
_FIRST_TOKEN_AND_CADENCE_EMIT_COUNT = 2


class _FakeChatStream:
    """A `ChatStream` double yielding canned chunks, then a trailing response."""

    def __init__(self, *, chunks: tuple[ChatChunk, ...], response: ChatResponse) -> None:
        self._chunks = chunks
        self._response = response

    def __iter__(self) -> Iterator[ChatChunk]:
        return iter(self._chunks)

    def __next__(self) -> ChatChunk:  # pragma: no cover — iteration goes via __iter__
        raise StopIteration

    def trailing_response(self) -> ChatResponse:
        return self._response


class _RaisingChatStream:
    """A `ChatStream` double whose iteration raises a given exception."""

    def __init__(self, *, exc: Exception) -> None:
        self._exc = exc

    def __iter__(self) -> Iterator[ChatChunk]:
        return self

    def __next__(self) -> ChatChunk:
        raise self._exc

    def trailing_response(self) -> ChatResponse:  # pragma: no cover — never reached
        raise AssertionError("trailing_response must not be called when iteration raises")


class _ManualClock:
    """A `Clock` double whose monotonic time advances only when told to."""

    def __init__(self) -> None:
        self._monotonic_ms = 0
        self._now = datetime(2026, 1, 1, tzinfo=UTC)

    def now_utc(self) -> Iso8601Utc:
        return self._now.isoformat()

    def monotonic_ms(self) -> int:
        return self._monotonic_ms

    def advance(self, ms: int) -> None:
        self._monotonic_ms += ms


class _NoopSubscription:
    """A `Subscription` double; never cancelled in this module's tests."""

    def cancel(self) -> None:  # pragma: no cover — unused in this module's tests
        pass


class _RecordingEventBus:
    """An `EventBus` double recording every emitted signal name and payload."""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, InferenceProgressEvent]] = []

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> Subscription:
        del signal_name, handler, owner  # unused: no test in this module subscribes
        return _NoopSubscription()

    def emit(self, signal_name: str, payload: object) -> None:
        assert isinstance(payload, InferenceProgressEvent)
        self.emitted.append((signal_name, payload))


def _make_token(clock: Clock) -> CancellationToken:
    return CancellationToken(clock=clock)


def test_emits_immediately_on_first_content_token() -> None:
    """First content chunk triggers an immediate emission, with no cadence wait."""
    clock = _ManualClock()
    bus = _RecordingEventBus()
    chat_stream = _FakeChatStream(
        chunks=(ChatChunk(content="Paris", delta_tokens=1),),
        response=ChatResponse(text="Paris", total_time_ms=100),
    )

    emit_progress_during(
        chat_stream,
        context=InferenceContext.BENCHMARK_TASK,
        run_id=_RUN_ID,
        result_id=_RESULT_ID,
        task_id=_TASK_ID,
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        clock=clock,
        event_bus=bus,
        token=_make_token(clock),
    )

    assert len(bus.emitted) == 1
    signal_name, payload = bus.emitted[0]
    assert signal_name == "_inference_progress"
    assert payload.first_token_received is True


def test_tokens_received_is_none_before_first_token() -> None:
    """A chunk with no content (no token yet) never triggers an emission."""
    clock = _ManualClock()
    bus = _RecordingEventBus()
    chat_stream = _FakeChatStream(
        chunks=(ChatChunk(content="", delta_tokens=None),),
        response=ChatResponse(text="", total_time_ms=100),
    )

    emit_progress_during(
        chat_stream,
        context=InferenceContext.BENCHMARK_TASK,
        run_id=_RUN_ID,
        result_id=_RESULT_ID,
        task_id=_TASK_ID,
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        clock=clock,
        event_bus=bus,
        token=_make_token(clock),
    )

    assert bus.emitted == []


def test_emits_at_cadence_during_a_multi_chunk_stream() -> None:
    """A second emission fires once >= 1000ms has elapsed since the last one."""
    clock = _ManualClock()
    bus = _RecordingEventBus()
    second_chunk_index = 2

    class _CadenceStream:
        def __init__(self) -> None:
            self._chunks = [
                ChatChunk(content="A", delta_tokens=1),
                ChatChunk(content="B", delta_tokens=1),
            ]
            self._index = 0

        def __iter__(self) -> Iterator[ChatChunk]:
            return self

        def __next__(self) -> ChatChunk:
            if self._index >= len(self._chunks):
                raise StopIteration
            chunk = self._chunks[self._index]
            self._index += 1
            if self._index == second_chunk_index:
                clock.advance(1500)
            return chunk

        def trailing_response(self) -> ChatResponse:
            return ChatResponse(text="AB", total_time_ms=1500)

    emit_progress_during(
        _CadenceStream(),
        context=InferenceContext.BENCHMARK_TASK,
        run_id=_RUN_ID,
        result_id=_RESULT_ID,
        task_id=_TASK_ID,
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        clock=clock,
        event_bus=bus,
        token=_make_token(clock),
    )

    assert len(bus.emitted) == _FIRST_TOKEN_AND_CADENCE_EMIT_COUNT


def test_stops_emitting_once_the_stream_ends() -> None:
    """No further event fires once iteration has completed and the helper returned."""
    clock = _ManualClock()
    bus = _RecordingEventBus()
    chat_stream = _FakeChatStream(
        chunks=(ChatChunk(content="Paris", delta_tokens=1),),
        response=ChatResponse(text="Paris", total_time_ms=100),
    )

    emit_progress_during(
        chat_stream,
        context=InferenceContext.BENCHMARK_TASK,
        run_id=_RUN_ID,
        result_id=_RESULT_ID,
        task_id=_TASK_ID,
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        clock=clock,
        event_bus=bus,
        token=_make_token(clock),
    )
    emitted_snapshot = list(bus.emitted)

    assert bus.emitted == emitted_snapshot


def test_propagates_task_cancelled_error_mid_stream() -> None:
    """`raise_if_cancelled()` firing mid-stream propagates `TaskCancelledError`."""
    clock = _ManualClock()
    bus = _RecordingEventBus()
    token = _make_token(clock)
    token.cancel(reason=CancelReason.USER_STOP)
    chat_stream = _FakeChatStream(
        chunks=(ChatChunk(content="Paris", delta_tokens=1),),
        response=ChatResponse(text="Paris", total_time_ms=100),
    )

    with pytest.raises(TaskCancelledError):
        emit_progress_during(
            chat_stream,
            context=InferenceContext.BENCHMARK_TASK,
            run_id=_RUN_ID,
            result_id=_RESULT_ID,
            task_id=_TASK_ID,
            provider_id=_PROVIDER_ID,
            model_name=_MODEL_NAME,
            clock=clock,
            event_bus=bus,
            token=token,
        )


def test_propagates_a_taxonomy_leaf_raised_by_the_stream_unchanged() -> None:
    """A taxonomy leaf raised by the stream iterator propagates unconverted — this
    helper "catches nothing"."""
    clock = _ManualClock()
    bus = _RecordingEventBus()
    chat_stream = _RaisingChatStream(exc=HttpConnectionError(message="connection reset"))

    with pytest.raises(HttpConnectionError):
        emit_progress_during(
            chat_stream,
            context=InferenceContext.BENCHMARK_TASK,
            run_id=_RUN_ID,
            result_id=_RESULT_ID,
            task_id=_TASK_ID,
            provider_id=_PROVIDER_ID,
            model_name=_MODEL_NAME,
            clock=clock,
            event_bus=bus,
            token=_make_token(clock),
        )
