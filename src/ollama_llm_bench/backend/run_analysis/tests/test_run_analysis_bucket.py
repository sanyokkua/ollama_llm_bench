"""Proves: STORY-035-AC-5"""

from ollama_llm_bench.backend.adaptive_timeout.protocols import AdaptiveTimeoutService
from ollama_llm_bench.backend.domain import (
    AdaptiveTimeoutRole,
    BenchmarkRunModelEntry,
    ChatResponse,
    ModelRole,
)
from ollama_llm_bench.backend.persistence.results.testing import FakeResultsStore
from ollama_llm_bench.backend.run_analysis._internal.timeout_cache import RunAdaptiveTimeoutCache
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
_RUN_ANALYSIS_MIN_SECONDS = 20
_JUDGE_CONSECUTIVE_THRESHOLD = 2
_MS_PER_SECOND = 1000
_MAX_DRIVE_ATTEMPTS = 10


def _drive_bucket_to_exclusion(
    adaptive_timeout: AdaptiveTimeoutService, role: AdaptiveTimeoutRole
) -> None:
    """Escalate ``(provider, model, role)`` through consecutive timeouts until excluded."""
    for attempt_index in range(1, _MAX_DRIVE_ATTEMPTS + 1):
        adaptive_timeout.next_budget(_PROVIDER_ID, _MODEL_NAME, role, attempt_index)
        adaptive_timeout.record_timeout(_PROVIDER_ID, _MODEL_NAME, role)
        if adaptive_timeout.is_excluded(_PROVIDER_ID, _MODEL_NAME, role):
            return
    raise AssertionError(f"bucket did not reach EXCLUDED within {_MAX_DRIVE_ATTEMPTS} attempts")


def test_same_run_id_reuses_the_same_service_instance() -> None:
    """Proves: RA-25 (cross-call last-known-good persistence)

    Two lookups for the same run_id return the identical AdaptiveTimeoutService
    object, so a promoted last-known-good survives from one generate() call to
    the next; a different run_id gets an independent instance.
    """
    cache = RunAdaptiveTimeoutCache()
    snapshot = build_run_analysis_snapshot()
    first = cache.get_or_create(run_id=1, snapshot=snapshot)
    second = cache.get_or_create(run_id=1, snapshot=snapshot)
    other_run = cache.get_or_create(run_id=2, snapshot=snapshot)
    assert first is second
    assert first is not other_run


def test_run_analysis_bucket_is_independent_of_judge() -> None:
    """Proves: STORY-035-AC-5

    Covers RA-22, RA-24. The analysis call consults next_budget/record_success/
    record_timeout with role=RUN_ANALYSIS, never role=JUDGE; a real
    AdaptiveTimeoutService already driven to its role=JUDGE ceiling by a prior
    BENCHMARK_RUN-style call sequence does not change when generate() runs — the
    JUDGE bucket's is_excluded state is untouched after generate() completes, and
    the RUN_ANALYSIS attempt starts from its own fresh minimum, not JUDGE's ceiling.
    """
    task = make_task(task_id="t1")
    snapshot = build_run_analysis_snapshot(
        judge_min_seconds=_RUN_ANALYSIS_MIN_SECONDS,
        judge_max_seconds=120,
        judge_escalation_steps=2,
        judge_consecutive_threshold=_JUDGE_CONSECUTIVE_THRESHOLD,
    )
    run = make_run(
        models=(
            BenchmarkRunModelEntry(
                role=ModelRole.TEST, provider_id=_PROVIDER_ID, model_name=_MODEL_NAME
            ),
        ),
        settings_snapshot=snapshot,
    )
    results = (make_result(task_id="t1", provider_id=_PROVIDER_ID, model_name=_MODEL_NAME),)

    timeout_cache = RunAdaptiveTimeoutCache()
    adaptive_timeout = timeout_cache.get_or_create(run_id=run.run_id, snapshot=snapshot)
    _drive_bucket_to_exclusion(adaptive_timeout, AdaptiveTimeoutRole.JUDGE)
    assert (
        adaptive_timeout.is_excluded(_PROVIDER_ID, _MODEL_NAME, AdaptiveTimeoutRole.JUDGE) is True
    )

    llm_client = FakeLLMClient()
    llm_client.queue_chat_stream(
        StaticChatStream(response=ChatResponse(text="# Overview\n...", total_time_ms=100))
    )
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
        timeout_cache=timeout_cache,
    )

    result = service.generate(run.run_id, _PROVIDER_ID, _MODEL_NAME, inside_pipeline=False)

    assert result.outcome == RunAnalysisOutcome.GENERATED
    assert llm_client.chat_stream_calls[0].timeout_ms == _RUN_ANALYSIS_MIN_SECONDS * _MS_PER_SECOND
    assert (
        adaptive_timeout.is_excluded(_PROVIDER_ID, _MODEL_NAME, AdaptiveTimeoutRole.JUDGE) is True
    )
    assert (
        adaptive_timeout.is_excluded(_PROVIDER_ID, _MODEL_NAME, AdaptiveTimeoutRole.RUN_ANALYSIS)
        is False
    )
