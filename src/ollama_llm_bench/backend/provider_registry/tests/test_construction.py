"""Construction and routing tests for ``ProviderRegistryImpl``.

Source of truth: ``docs/stories/story-017-provider-registry-and-llm-client-protocol.md``
STORY-017-AC-1, STORY-017-AC-2.
"""

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderType
from ollama_llm_bench.backend.events.models import SIGNAL_PROVIDER_REGISTRY_RELOADED
from ollama_llm_bench.backend.provider_registry.api import make_provider_registry
from ollama_llm_bench.backend.provider_registry.protocols import ClientBuilder
from ollama_llm_bench.backend.provider_registry.tests.conftest import (
    FakeEventBus,
    FakeLLMClient,
    FakeProvidersStore,
    make_provider_config,
)
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore


def test_registry_lists_enabled_and_routes_each_provider(
    fake_providers_store: FakeProvidersStore,
    client_builders: dict[ProviderType, ClientBuilder],
    gate: FakeInferenceActivityStore,
    fake_event_bus: FakeEventBus,
) -> None:
    """Proves: STORY-017-AC-1

    Given a catalog of three enabled, structurally valid providers whose
    secrets resolve, when the registry is constructed, then ``list_enabled()``
    returns all three in ``provider_order`` and ``get_client`` returns a
    distinct client instance for each. Construction also emits no
    ``_provider_registry_reloaded`` event — that event is reserved for
    ``reload()`` only (§6.6; ``08-Q_event_payload_schemas.md``'s
    ``reload_cause`` enum has no "startup" value).
    """
    # Arrange
    provider_a = make_provider_config(
        provider_id="11111111-1111-4111-8111-111111111111", name="a", provider_order=0
    )
    provider_b = make_provider_config(
        provider_id="22222222-2222-4222-8222-222222222222", name="b", provider_order=1
    )
    provider_c = make_provider_config(
        provider_id="33333333-3333-4333-8333-333333333333", name="c", provider_order=2
    )
    fake_providers_store.set_providers((provider_a, provider_b, provider_c))

    # Act
    registry = make_provider_registry(
        providers_store=fake_providers_store,
        client_builders=client_builders,
        gate=gate,
        event_bus=fake_event_bus,
    )

    # Assert
    enabled = registry.list_enabled()
    assert enabled == (provider_a, provider_b, provider_c)
    client_a = registry.get_client(provider_a.provider_id)
    client_b = registry.get_client(provider_b.provider_id)
    client_c = registry.get_client(provider_c.provider_id)
    distinct_client_ids = {id(client_a), id(client_b), id(client_c)}
    assert len(distinct_client_ids) == len((client_a, client_b, client_c))
    assert fake_event_bus.emitted_count(SIGNAL_PROVIDER_REGISTRY_RELOADED) == 0


def test_routing_is_by_provider_id_not_model_name(
    fake_providers_store: FakeProvidersStore,
    gate: FakeInferenceActivityStore,
    fake_event_bus: FakeEventBus,
) -> None:
    """Proves: STORY-017-AC-2

    Given two enabled providers with different ``provider_id`` that both
    expose the model name ``model_x``, when ``get_client`` is called for
    each, then each returns a distinct client and the model name is never
    consulted to select the client — routing is by ``provider_id`` alone.
    """
    # Arrange
    provider_one = make_provider_config(
        provider_id="11111111-1111-4111-8111-111111111111",
        name="provider-one",
    )
    provider_two = make_provider_config(
        provider_id="22222222-2222-4222-8222-222222222222",
        name="provider-two",
    )
    fake_providers_store.set_providers((provider_one, provider_two))
    built_clients: dict[str, FakeLLMClient] = {}

    def _factory(provider: ProviderConfig, resolved_api_key: str) -> FakeLLMClient:
        client = FakeLLMClient(provider=provider, resolved_api_key=resolved_api_key)
        built_clients[provider.provider_id] = client
        return client

    builders: dict[ProviderType, ClientBuilder] = dict.fromkeys(ProviderType, _factory)

    # Act
    registry = make_provider_registry(
        providers_store=fake_providers_store,
        client_builders=builders,
        gate=gate,
        event_bus=fake_event_bus,
    )
    client_one = registry.get_client(provider_one.provider_id)
    client_two = registry.get_client(provider_two.provider_id)

    # Assert
    assert client_one is built_clients[provider_one.provider_id]
    assert client_two is built_clients[provider_two.provider_id]
    assert client_one is not client_two
