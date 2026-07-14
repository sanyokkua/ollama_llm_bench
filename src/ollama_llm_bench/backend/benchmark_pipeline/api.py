"""Public factory for `backend/benchmark_pipeline/`: the run-engine composition point."""

import icontract

from ollama_llm_bench.backend.benchmark_pipeline._internal.lifecycle import _BenchmarkFlowApiImpl
from ollama_llm_bench.backend.benchmark_pipeline.protocols import BenchmarkFlowApi
from ollama_llm_bench.backend.concurrency.protocols import TaskRunner
from ollama_llm_bench.backend.domain.models import ResultPatch
from ollama_llm_bench.backend.embedding.protocols import EmbeddingService
from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.results.protocols import ResultsStore
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.persistence.tasks.protocols import TasksStore
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry
from ollama_llm_bench.backend.settings.protocols import RunSnapshotBuilder, SettingsService
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore

__all__: list[str] = ["make_benchmark_pipeline"]


@icontract.ensure(
    lambda result: result is not None,
    "make_benchmark_pipeline must always return a usable BenchmarkFlowApi — a violation "
    "here means this factory's own wiring is broken, not that a caller passed bad input",
)
def make_benchmark_pipeline(  # noqa: PLR0913  # every keyword-only argument is a distinct,
    # already-Protocol-typed collaborator the composition root wires through to the single
    # lifecycle controller this module exposes (project-structure.md's "one implementation
    # with constructor configuration" module shape) — bundling them into a struct would only
    # indirect the read without reducing real coupling
    *,
    results_store: ResultsStore,
    runs_store: RunsStore,
    tasks_store: TasksStore,
    inference_activity_store: InferenceActivityStore,
    task_runner: TaskRunner[object],
    bus: EventBus,
    clock: Clock,
    embedding_service: EmbeddingService,
    provider_registry: ProviderRegistry,
    settings_service: SettingsService,
    run_snapshot_builder: RunSnapshotBuilder,
) -> BenchmarkFlowApi:
    """Construct the benchmark pipeline's lifecycle controller for one composition root.

    Args:
        results_store: The single-writer per-task result-row store.
        runs_store: The single-writer run-header store.
        tasks_store: The run's frozen task-snapshot store.
        inference_activity_store: The application-wide single-inference gate.
        task_runner: The scheduling port each phase's units are submitted to.
            Typed `TaskRunner[object]` (mirroring `backend/readiness`) since
            it serves every phase's distinct per-unit payload type — the
            non-stability phases' own `ResultPatch` read is cast back
            internally.
        bus: The application event bus run-domain and per-task events are emitted on.
        clock: The injected time source.
        embedding_service: The shared embedding + cosine-scoring facade.
        provider_registry: Resolves a run's models to live `LLMClient` instances.
        settings_service: Typed access to the three-layer settings hierarchy.
        run_snapshot_builder: Captures a new run's frozen per-run-overridable settings.

    Returns:
        A `BenchmarkFlowApi` implementation admitting runs under the
        single-inference gate and driving them through the five-phase batched
        pipeline on the dedicated dispatcher thread; never raises to its
        caller.
    """
    return _BenchmarkFlowApiImpl(
        results_store=results_store,
        runs_store=runs_store,
        tasks_store=tasks_store,
        inference_activity_store=inference_activity_store,
        task_runner=task_runner,
        bus=bus,
        clock=clock,
        embedding_service=embedding_service,
        provider_registry=provider_registry,
        settings_service=settings_service,
        run_snapshot_builder=run_snapshot_builder,
    )
