"""Proves: STORY-035-AC-2"""

import pytest

from ollama_llm_bench.backend.domain import (
    BenchmarkRunModelEntry,
    ChatResponse,
    ModelRole,
    ResultStatus,
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


@pytest.mark.parametrize(
    ("snapshot_enabled", "is_user_initiated", "result_count", "expected_outcome"),
    [
        (True, False, 3, None),
        (False, False, 3, RunAnalysisOutcome.SKIPPED),
        (True, True, 0, RunAnalysisOutcome.SKIPPED),
        (False, True, 3, None),
        (True, False, 0, RunAnalysisOutcome.SKIPPED),
    ],
)
def test_applicability_gate_branches(
    *,
    snapshot_enabled: bool,
    is_user_initiated: bool,
    result_count: int,
    expected_outcome: RunAnalysisOutcome | None,
) -> None:
    """Proves: STORY-035-AC-2

    Covers RA-01, RA-01b, RA-02, RA-04, RA-05 — the automatic path SKIPs when the
    snapshot flag is false; the user-initiated path always proceeds; zero terminal
    results SKIPs regardless of path.
    """
    task = make_task(task_id="t1")
    run = make_run(
        models=(
            BenchmarkRunModelEntry(
                role=ModelRole.TEST, provider_id=_PROVIDER_ID, model_name=_MODEL_NAME
            ),
        ),
        settings_snapshot=build_run_analysis_snapshot(judge_run_analysis_enabled=snapshot_enabled),
    )
    results = tuple(
        make_result(
            result_id=i,
            task_id="t1",
            provider_id=_PROVIDER_ID,
            model_name=_MODEL_NAME,
            status=ResultStatus.COMPLETED,
        )
        for i in range(result_count)
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
    )

    result = service.generate(
        run.run_id, _PROVIDER_ID, _MODEL_NAME, inside_pipeline=not is_user_initiated
    )

    if expected_outcome is not None:
        assert result.outcome == expected_outcome
        assert llm_client.chat_stream_calls == []
    else:
        assert llm_client.chat_stream_calls != []
