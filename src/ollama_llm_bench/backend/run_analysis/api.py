"""Public factory for the Run Analysis Service (§2.1)."""

import icontract

from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.results.protocols import ResultsStore
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.persistence.tasks.protocols import TasksStore
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry
from ollama_llm_bench.backend.run_analysis._internal.service import RunAnalysisServiceImpl
from ollama_llm_bench.backend.run_analysis._internal.timeout_cache import RunAdaptiveTimeoutCache
from ollama_llm_bench.backend.run_analysis.protocols import RunAnalysisService
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore

__all__: list[str] = ["make_run_analysis_service"]


@icontract.require(lambda clock: clock is not None, "clock must be supplied by compose.py")
def make_run_analysis_service(  # noqa: PLR0913  # constructor injection — every dependency is distinct
    *,
    runs_store: RunsStore,
    results_store: ResultsStore,
    tasks_store: TasksStore,
    provider_registry: ProviderRegistry,
    inference_activity_store: InferenceActivityStore,
    event_bus: EventBus,
    clock: Clock,
) -> RunAnalysisService:
    """Construct the Run Analysis Service (§2.1).

    Args:
        runs_store: Loads the run header and applies no writes — this service
            never persists.
        results_store: Loads the run's ``BenchmarkResult`` rows.
        tasks_store: Loads the run's ``BenchmarkTask`` rows for digest aggregation.
        provider_registry: Resolves the chosen ``(provider_id, model_name)`` to an
            ``LLMClient``.
        inference_activity_store: The application-wide single-inference gate.
        event_bus: Publishes ``_inference_progress`` events during the call.
        clock: The injected time source.

    Returns:
        A ``RunAnalysisService`` holding one internal ``RunId -> AdaptiveTimeoutService``
        cache for the lifetime of the returned instance (see ``timeout_cache.py``).
    """
    return RunAnalysisServiceImpl(
        runs_store=runs_store,
        results_store=results_store,
        tasks_store=tasks_store,
        provider_registry=provider_registry,
        inference_activity_store=inference_activity_store,
        event_bus=event_bus,
        clock=clock,
        timeout_cache=RunAdaptiveTimeoutCache(),
    )
