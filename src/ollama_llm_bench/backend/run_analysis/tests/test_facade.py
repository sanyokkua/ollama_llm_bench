"""Proves the module's public surface is importable and the factory constructs cleanly."""

from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.results.protocols import ResultsStore
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.persistence.tasks.protocols import TasksStore
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry
from ollama_llm_bench.backend.run_analysis import RunAnalysisResult, make_run_analysis_service
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore


def test_make_run_analysis_service_returns_a_protocol_conforming_instance(  # noqa: PLR0913  # every project fixture is load-bearing for the wiring proof
    fake_runs_store: RunsStore,
    fake_results_store: ResultsStore,
    fake_tasks_store: TasksStore,
    fake_provider_registry: ProviderRegistry,
    fake_inference_activity_store: InferenceActivityStore,
    fake_event_bus: EventBus,
    fake_clock: Clock,
) -> None:
    """Proves: STORY-035-AC-1 (facade wiring, not outcome behavior — see service tests for that)"""
    service = make_run_analysis_service(
        runs_store=fake_runs_store,
        results_store=fake_results_store,
        tasks_store=fake_tasks_store,
        provider_registry=fake_provider_registry,
        inference_activity_store=fake_inference_activity_store,
        event_bus=fake_event_bus,
        clock=fake_clock,
    )
    assert hasattr(service, "generate")
    result = service.generate(1, "p1", "m1")
    assert isinstance(result, RunAnalysisResult)
