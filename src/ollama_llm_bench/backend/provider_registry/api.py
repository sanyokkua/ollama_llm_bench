"""Public factory for ``backend/provider_registry/``.

The composition root constructs this registry once, over the shared providers store,
the per-``ProviderType`` client-builder callables assembled from the concrete adapter
factories, the single-inference gate, and the event bus, and injects it wherever a
``ProviderRegistry`` is needed. A run-scoped registry (built from a frozen
``BenchmarkRun`` provider snapshot rather than the live catalog) is constructed the same
way, over a run-scoped ``ProvidersStore``-shaped collaborator.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§9; ``docs/v3_specification/11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md`` §6.1.
"""

from collections.abc import Mapping

import icontract

from ollama_llm_bench.backend.domain import ProviderType
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.persistence.providers import ProvidersStore
from ollama_llm_bench.backend.provider_registry._internal.registry_impl import (
    ProviderRegistryCollaborators,
    ProviderRegistryImpl,
)
from ollama_llm_bench.backend.provider_registry.protocols import (
    ChatStream,
    ClientBuilder,
    LLMClient,
    ProviderRegistry,
)
from ollama_llm_bench.backend.stores.inference_activity import InferenceActivityStore

__all__: list[str] = [
    "ChatStream",
    "ClientBuilder",
    "LLMClient",
    "ProviderRegistry",
    "make_provider_registry",
]


@icontract.require(
    lambda providers_store: providers_store is not None,
    "providers_store is a required collaborator wired by compose.py",
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
    lambda client_builders: set(client_builders.keys()) == set(ProviderType),
    "compose.py must wire a builder for every ProviderType; a missing builder is a "
    "wiring bug, not a runtime condition",
)
@icontract.ensure(
    lambda result, providers_store: (
        len(result.list_enabled()) <= len(providers_store.list_providers())
    ),
    "the enabled subset can never exceed the full catalog just read from the store",
)
def make_provider_registry(
    *,
    providers_store: ProvidersStore,
    client_builders: Mapping[ProviderType, ClientBuilder],
    gate: InferenceActivityStore,
    event_bus: EventBus,
) -> ProviderRegistry:
    """Construct the concrete ``ProviderRegistry`` over its collaborators.

    Performs the first build synchronously before returning (§6.2): the
    constructed registry's client map already reflects the current provider
    catalog.

    Args:
        providers_store: The read-only source of the provider catalog this
            registry rebuilds its clients from.
        client_builders: The per-``ProviderType`` constructor callables,
            wired from the concrete adapter factories in ``compose.py``. Must
            cover every ``ProviderType`` member.
        gate: The application-wide single-inference gate; a superseded
            client map is closed immediately when this gate is idle at swap
            time, or deferred until the next idle transition otherwise
            (SPEC-045).
        event_bus: The bus ``_provider_registry_reloaded`` is emitted on
            after a successful rebuild, and the bus this registry subscribes
            to for ``_inference_activity_changed`` (the deferred-close
            trigger).

    Returns:
        A ``ProviderRegistry`` whose client map already reflects the current
        provider catalog.

    Raises:
        ConfigurationError: An enabled provider in the initial catalog is
            structurally invalid.
        PersistenceError: The initial ``ProvidersStore.list_providers()``
            read failed.
    """
    collaborators = ProviderRegistryCollaborators(
        providers_store=providers_store,
        client_builders=client_builders,
        gate=gate,
        event_bus=event_bus,
    )
    return ProviderRegistryImpl(collaborators=collaborators)
