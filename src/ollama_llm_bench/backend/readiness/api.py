"""Public factory for ``backend/readiness/``.

The composition root constructs this service once over the shared collaborators
and injects it wherever a ``ReadinessService`` is needed — the status-bar health
dot, the New Benchmark widget's pre-run gate, and the Settings dialog's readiness
section all read the same instance's ``snapshot()``/``probe_all()``.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§12.
"""

import icontract

from ollama_llm_bench.backend.concurrency import TaskRunner
from ollama_llm_bench.backend.domain import ReadinessState
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.readiness._internal.service import (
    ReadinessServiceCollaborators,
    ReadinessServiceImpl,
)
from ollama_llm_bench.backend.readiness.protocols import (
    ReadinessEmbeddingSelector,
    ReadinessProviderRegistry,
    ReadinessService,
)
from ollama_llm_bench.backend.settings import SettingsService
from ollama_llm_bench.backend.stores.inference_activity import InferenceActivityStore

__all__: list[str] = [
    "ReadinessEmbeddingSelector",
    "ReadinessProviderRegistry",
    "ReadinessService",
    "make_readiness_service",
]


@icontract.require(
    lambda registry: registry is not None,
    "registry is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda embedding_selector: embedding_selector is not None,
    "embedding_selector is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda settings: settings is not None,
    "settings is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda gate: gate is not None,
    "gate is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda event_bus: event_bus is not None,
    "event_bus is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda task_runner: task_runner is not None,
    "task_runner is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda clock: clock is not None,
    "clock is a required collaborator wired by compose.py",
)
@icontract.ensure(
    lambda result: result.snapshot().overall == ReadinessState.CHECKING,
    "a freshly constructed ReadinessService always starts CHECKING before its first probe",
)
def make_readiness_service(  # noqa: PLR0913  # the composition-root factory for a
    # service with seven required Protocol collaborators; each is independently
    # swappable in compose.py, so a single bundle param would only hide the wiring
    *,
    registry: ReadinessProviderRegistry,
    embedding_selector: ReadinessEmbeddingSelector,
    settings: SettingsService,
    gate: InferenceActivityStore,
    event_bus: EventBus,
    task_runner: TaskRunner[object],
    clock: Clock,
) -> ReadinessService:
    """Construct the concrete ``ReadinessService`` over its collaborators.

    Args:
        registry: Looks up enabled providers and their live clients.
        embedding_selector: Resolves the live embedding-model selection for
            the handshake-only probe (DD-48).
        settings: Resolves ``provider.probe_timeout_ms``, the per-probe
            deadline shared with ``LLMClient.probe_health``.
        gate: The application-wide single-inference gate; every probe
            acquires ``InferenceActivity.READINESS_PROBE`` before any
            network call and releases it in ``finally``.
        event_bus: The bus ``_app_readiness_changed`` is emitted on after a
            batch that actually changed the cached snapshot.
        task_runner: The shared ``TaskRunner`` the batch fans its per-provider
            reachability handshakes out to, and submits the single embedding
            probe unit to.
        clock: The injected time source for probe timestamps and the
            per-batch ``CancellationToken``.

    Returns:
        A ``ReadinessService`` whose cached snapshot starts ``CHECKING`` and
        is refreshed only by ``probe_all()``.
    """
    collaborators = ReadinessServiceCollaborators(
        registry=registry,
        embedding_selector=embedding_selector,
        settings=settings,
        gate=gate,
        event_bus=event_bus,
        task_runner=task_runner,
        clock=clock,
    )
    return ReadinessServiceImpl(collaborators=collaborators)
