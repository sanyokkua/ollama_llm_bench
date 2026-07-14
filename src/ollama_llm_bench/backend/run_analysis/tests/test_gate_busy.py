"""Proves: STORY-035-AC-3"""

from ollama_llm_bench.backend.domain import (
    BenchmarkRunModelEntry,
    InferenceActivity,
    InferenceActivityContext,
    ModelRole,
)
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.run_analysis.models import RunAnalysisOutcome
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


def test_gate_busy_returns_failed_without_model_call() -> None:
    """Proves: STORY-035-AC-3

    Covers RA-20. A user-initiated generate() while another activity holds the
    gate returns FAILED with the busy message and never calls the LLM client.
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
    clock = FakeClock()
    event_bus = FakeEventBus()
    inference_activity_store = FakeInferenceActivityStore(clock=clock, event_bus=event_bus)
    inference_activity_store.try_acquire(
        InferenceActivity.PROVIDER_TEST,
        InferenceActivityContext(activity=InferenceActivity.PROVIDER_TEST, started_at=0),
    )
    service = make_service(
        runs_store=FakeRunsStore(run=run),
        results_store=FakeResultsStore(initial=results),
        tasks_store=FakeTasksStore(tasks=(task,)),
        provider_registry=FakeProviderRegistry(client=llm_client),
        inference_activity_store=inference_activity_store,
        event_bus=event_bus,
        clock=clock,
    )

    result = service.generate(run.run_id, _PROVIDER_ID, _MODEL_NAME, inside_pipeline=False)

    assert result.outcome == RunAnalysisOutcome.FAILED
    assert "in flight" in (result.error_message or "").lower()
    assert llm_client.chat_stream_calls == []
