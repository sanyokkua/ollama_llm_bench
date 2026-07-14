"""Proves: STORY-035-AC-7"""

from ollama_llm_bench.backend.domain import (
    BenchmarkRunModelEntry,
    BenchmarkRunSettingEntry,
    ChatResponse,
    ModelRole,
)
from ollama_llm_bench.backend.errors import HttpConnectionError, HttpTimeoutError
from ollama_llm_bench.backend.events.models import SIGNAL_JUDGE_MODEL_EXCLUDED
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.run_analysis._internal.service import RunAnalysisServiceImpl
from ollama_llm_bench.backend.run_analysis.models import RunAnalysisOutcome
from ollama_llm_bench.backend.run_analysis.tests.conftest import (
    FakeClock,
    FakeEventBus,
    FakeLLMClient,
    FakeProviderRegistry,
    FakeRunsStore,
    FakeTasksStore,
    StaticChatStream,
    build_run_analysis_snapshot,
    make_result,
    make_run,
    make_service,
    make_task,
)
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

_PROVIDER_ID = "p1"
_MODEL_NAME = "m1"


def _build_service(
    llm_client: FakeLLMClient,
    *,
    snapshot: tuple[BenchmarkRunSettingEntry, ...] | None = None,
) -> tuple[RunAnalysisServiceImpl, FakeEventBus]:
    task = make_task(task_id="t1")
    run = make_run(
        models=(
            BenchmarkRunModelEntry(
                role=ModelRole.TEST, provider_id=_PROVIDER_ID, model_name=_MODEL_NAME
            ),
        ),
        settings_snapshot=snapshot,
    )
    results = (make_result(task_id="t1", provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),)
    clock = FakeClock()
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
    return service, event_bus


def test_non_timeout_error_fails_immediately_without_escalation() -> None:
    """Proves: STORY-035-AC-7

    Covers RA-06. A non-timeout transport/provider error on the first attempt
    returns FAILED immediately, with only ONE attempt made (no escalation).
    """
    llm_client = FakeLLMClient()
    llm_client.queue_chat_stream(HttpConnectionError(message="connection reset"))
    service, _ = _build_service(llm_client)

    result = service.generate(1, _PROVIDER_ID, _MODEL_NAME, inside_pipeline=False)

    assert result.outcome == RunAnalysisOutcome.FAILED
    assert result.error_message is not None
    assert len(llm_client.chat_stream_calls) == 1


def test_timeout_exhaustion_fails_with_no_exclusion_event() -> None:
    """Proves: STORY-035-AC-7

    Covers RA-07, RA-08, RA-10, RA-23. The RUN_ANALYSIS escalation ladder
    exhausted by consecutive timeouts returns FAILED with error_message
    containing "judge_timeout_exhausted", and no `_judge_model_excluded`
    event is ever emitted on the event bus.
    """
    consecutive_threshold = 3
    snapshot = build_run_analysis_snapshot(
        judge_min_seconds=20,
        judge_max_seconds=120,
        judge_escalation_steps=consecutive_threshold - 1,
        judge_consecutive_threshold=consecutive_threshold,
    )
    llm_client = FakeLLMClient()
    for _ in range(consecutive_threshold):
        llm_client.queue_chat_stream(HttpTimeoutError(message="timed out"))
    service, event_bus = _build_service(llm_client, snapshot=snapshot)

    result = service.generate(1, _PROVIDER_ID, _MODEL_NAME, inside_pipeline=False)

    assert result.outcome == RunAnalysisOutcome.FAILED
    assert "judge_timeout_exhausted" in (result.error_message or "")
    assert all(signal_name != SIGNAL_JUDGE_MODEL_EXCLUDED for signal_name, _ in event_bus.emitted)


def test_empty_response_fails_as_a_single_attempt() -> None:
    """Proves: STORY-035-AC-7

    Covers RA-08. A soft empty-response failure (ChatResponse.error set, not an
    exception) returns FAILED with an explanatory message, counted as a single
    attempt — no escalation on this path.
    """
    llm_client = FakeLLMClient()
    llm_client.queue_chat_stream(
        StaticChatStream(response=ChatResponse(text="", total_time_ms=100, error="empty_response"))
    )
    service, _ = _build_service(llm_client)

    result = service.generate(1, _PROVIDER_ID, _MODEL_NAME, inside_pipeline=False)

    assert result.outcome == RunAnalysisOutcome.FAILED
    assert "empty_response" in (result.error_message or "")
    assert len(llm_client.chat_stream_calls) == 1
