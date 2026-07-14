"""Proves: STORY-035-AC-8"""

from collections.abc import Iterator

from ollama_llm_bench.backend.domain import (
    BenchmarkRunModelEntry,
    ChatChunk,
    ChatResponse,
    InferenceContext,
    ModelRole,
)
from ollama_llm_bench.backend.events.models import SIGNAL_INFERENCE_PROGRESS, InferenceProgressEvent
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.run_analysis.tests.conftest import (
    FakeClock,
    FakeEventBus,
    FakeLLMClient,
    FakeProviderRegistry,
    FakeRunsStore,
    FakeTasksStore,
    make_result,
    make_run,
    make_service,
    make_task,
)
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

_PROVIDER_ID = "p1"
_MODEL_NAME = "m1"
_RUN_ID = 1
_MIN_EMIT_COUNT = 2


class _CadenceChatStream:
    """Yields canned chunks, advancing a `FakeClock` past the cadence threshold
    between each one so `emit_progress_during` emits at every chunk boundary."""

    def __init__(
        self, *, clock: FakeClock, chunks: tuple[ChatChunk, ...], response: ChatResponse
    ) -> None:
        self._clock = clock
        self._remaining = list(chunks)
        self._response = response

    def __iter__(self) -> Iterator[ChatChunk]:
        return self

    def __next__(self) -> ChatChunk:
        if not self._remaining:
            raise StopIteration
        self._clock.advance_monotonic_ms(1500)
        return self._remaining.pop(0)

    def trailing_response(self) -> ChatResponse:
        """Return the canned completed response."""
        return self._response


def test_inference_progress_emitted_during_call() -> None:
    """Proves: STORY-035-AC-8

    Covers RA-21. While the model call is in flight, _inference_progress events fire
    with context=RUN_ANALYSIS, this run's run_id, result_id=None, task_id=None, and
    the chosen (provider_id, model_name); no event fires after the call ends.
    """
    task = make_task(task_id="t1")
    run = make_run(
        run_id=_RUN_ID,
        models=(
            BenchmarkRunModelEntry(
                role=ModelRole.TEST, provider_id=_PROVIDER_ID, model_name=_MODEL_NAME
            ),
        ),
    )
    results = (
        make_result(run_id=_RUN_ID, task_id="t1", provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),
    )
    clock = FakeClock()
    llm_client = FakeLLMClient()
    llm_client.queue_chat_stream(
        _CadenceChatStream(
            clock=clock,
            chunks=(
                ChatChunk(content="A", delta_tokens=1),
                ChatChunk(content="B", delta_tokens=1),
                ChatChunk(content="C", delta_tokens=1),
            ),
            response=ChatResponse(text="ABC", total_time_ms=4500),
        )
    )
    event_bus = FakeEventBus()
    service = make_service(
        runs_store=FakeRunsStore(run=run),
        results_store=FakeResultsStore(initial=results),
        tasks_store=FakeTasksStore(tasks=(task,)),
        provider_registry=FakeProviderRegistry(client=llm_client),
        inference_activity_store=FakeInferenceActivityStore(clock=clock, event_bus=event_bus),
        event_bus=event_bus,
        clock=clock,
    )

    service.generate(_RUN_ID, _PROVIDER_ID, _MODEL_NAME, inside_pipeline=False)

    progress_events = [
        payload
        for signal_name, payload in event_bus.emitted
        if signal_name == SIGNAL_INFERENCE_PROGRESS
    ]
    assert len(progress_events) >= _MIN_EMIT_COUNT
    for event in progress_events:
        assert isinstance(event, InferenceProgressEvent)
        assert event.context == InferenceContext.RUN_ANALYSIS
        assert event.run_id == _RUN_ID
        assert event.result_id is None
        assert event.task_id is None
        assert event.provider_id == _PROVIDER_ID
        assert event.model_name == _MODEL_NAME

    snapshot_count = len(progress_events)
    assert (
        len([p for s, p in event_bus.emitted if s == SIGNAL_INFERENCE_PROGRESS]) == snapshot_count
    )
