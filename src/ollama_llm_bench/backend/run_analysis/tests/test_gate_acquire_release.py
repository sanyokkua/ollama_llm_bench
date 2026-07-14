"""Proves: STORY-035-AC-4"""

import pytest

from ollama_llm_bench.backend.domain import (
    BenchmarkRunModelEntry,
    ChatResponse,
    GateLease,
    InferenceActivity,
    InferenceActivityContext,
    InferenceActivityState,
    ModelRole,
)
from ollama_llm_bench.backend.errors import HttpConnectionError
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.run_analysis.models import RunAnalysisOutcome
from ollama_llm_bench.backend.run_analysis.tests.conftest import (
    FakeClock,
    FakeEventBus,
    FakeLLMClient,
    FakeProviderRegistry,
    FakeRunsStore,
    FakeTasksStore,
    StaticChatStream,
    make_result,
    make_run,
    make_service,
    make_task,
)
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

_PROVIDER_ID = "p1"
_MODEL_NAME = "m1"


class _SpyInferenceActivityStore:
    """Wraps a real `FakeInferenceActivityStore`, recording every call."""

    def __init__(self, inner: FakeInferenceActivityStore) -> None:
        self._inner = inner
        self.try_acquire_calls: list[InferenceActivity] = []
        self.release_calls: list[GateLease] = []

    def try_acquire(
        self, activity: InferenceActivity, context: InferenceActivityContext
    ) -> GateLease | None:
        self.try_acquire_calls.append(activity)
        return self._inner.try_acquire(activity, context)

    def release(self, lease: GateLease) -> None:
        self.release_calls.append(lease)
        self._inner.release(lease)

    def state(self) -> InferenceActivityState:
        return self._inner.state()

    def is_busy(self) -> bool:
        return self._inner.is_busy()


@pytest.mark.parametrize(
    ("inside_pipeline", "model_raises"),
    [
        (True, False),
        (False, False),
        (False, True),
    ],
)
def test_in_pipeline_skips_acquire_user_path_releases(
    *, inside_pipeline: bool, model_raises: bool
) -> None:
    """Proves: STORY-035-AC-4

    Covers RA-19. In-pipeline call skips try_acquire and never releases; user-initiated
    call acquires JUDGE_ANALYSIS and releases in finally — including when the model call raises.
    """
    task = make_task(task_id="t1")
    run = make_run(
        models=(
            BenchmarkRunModelEntry(
                role=ModelRole.TEST, provider_id=_PROVIDER_ID, model_name=_MODEL_NAME
            ),
        )
    )
    results = (make_result(task_id="t1", provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),)
    llm_client = FakeLLMClient()
    if model_raises:
        llm_client.queue_chat_stream(HttpConnectionError(message="connection reset"))
    else:
        llm_client.queue_chat_stream(
            StaticChatStream(response=ChatResponse(text="# Overview\n...", total_time_ms=100))
        )
    clock = FakeClock()
    event_bus = FakeEventBus()
    spy = _SpyInferenceActivityStore(FakeInferenceActivityStore(clock=clock, event_bus=event_bus))
    service = make_service(
        runs_store=FakeRunsStore(run=run),
        results_store=FakeResultsStore(initial=results),
        tasks_store=FakeTasksStore(tasks=(task,)),
        provider_registry=FakeProviderRegistry(client=llm_client),
        inference_activity_store=spy,
        event_bus=event_bus,
        clock=clock,
    )

    result = service.generate(
        run.run_id, _PROVIDER_ID, _MODEL_NAME, inside_pipeline=inside_pipeline
    )

    if inside_pipeline:
        assert spy.try_acquire_calls == []
        assert spy.release_calls == []
    else:
        assert spy.try_acquire_calls == [InferenceActivity.JUDGE_ANALYSIS]
        assert len(spy.release_calls) == 1
        if model_raises:
            assert result.outcome == RunAnalysisOutcome.FAILED
        else:
            assert result.outcome == RunAnalysisOutcome.GENERATED
