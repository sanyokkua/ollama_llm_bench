"""``reload()`` atomicity tests for ``ProviderRegistryImpl``.

Source of truth: ``docs/stories/story-017-provider-registry-and-llm-client-protocol.md``
STORY-017-AC-6, STORY-017-AC-7.
"""

import pytest

from ollama_llm_bench.backend.domain import ProviderType
from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.events.models import SIGNAL_PROVIDER_REGISTRY_RELOADED
from ollama_llm_bench.backend.provider_registry.api import make_provider_registry
from ollama_llm_bench.backend.provider_registry.protocols import ClientBuilder
from ollama_llm_bench.backend.provider_registry.tests.conftest import (
    FakeEventBus,
    FakeProvidersStore,
    make_provider_config,
)
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

_VALID_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_BROKEN_PROVIDER_ID = "22222222-2222-4222-8222-222222222222"
_CLOUD_PROVIDER_ID = "33333333-3333-4333-8333-333333333333"


def test_reload_structural_failure_rolls_back_and_emits_nothing(
    fake_providers_store: FakeProvidersStore,
    client_builders: dict[ProviderType, ClientBuilder],
    gate: FakeInferenceActivityStore,
    fake_event_bus: FakeEventBus,
) -> None:
    """Proves: STORY-017-AC-6

    Given ``ProvidersStore`` returns a new catalog in which one enabled
    ``OPENAI_COMPATIBLE`` provider has an empty ``base_url`` and no Azure
    fields, when ``reload()`` runs, then it raises ``ConfigurationError``
    naming that provider, the previous catalog and client map remain exactly
    as they were, and no ``_provider_registry_reloaded`` event is emitted
    again.
    """
    # Arrange
    valid_provider = make_provider_config(provider_id=_VALID_PROVIDER_ID, name="valid")
    fake_providers_store.set_providers((valid_provider,))
    registry = make_provider_registry(
        providers_store=fake_providers_store,
        client_builders=client_builders,
        gate=gate,
        event_bus=fake_event_bus,
    )
    emitted_count_after_construction = fake_event_bus.emitted_count(
        SIGNAL_PROVIDER_REGISTRY_RELOADED
    )
    original_client = registry.get_client(_VALID_PROVIDER_ID)
    broken_provider = make_provider_config(
        provider_id=_BROKEN_PROVIDER_ID,
        name="broken",
        base_url="",
        azure_fields=(None, None, None),
    )
    fake_providers_store.set_providers((valid_provider, broken_provider))

    # Act
    with pytest.raises(ConfigurationError):
        registry.reload()

    # Assert
    assert registry.list_enabled() == (valid_provider,)
    assert registry.get_client(_VALID_PROVIDER_ID) is original_client
    with pytest.raises(ConfigurationError, match="unknown"):
        registry.get_client(_BROKEN_PROVIDER_ID)
    assert (
        fake_event_bus.emitted_count(SIGNAL_PROVIDER_REGISTRY_RELOADED)
        == emitted_count_after_construction
    )


def test_reload_omits_missing_env_provider_and_still_succeeds(
    fake_providers_store: FakeProvidersStore,
    client_builders: dict[ProviderType, ClientBuilder],
    gate: FakeInferenceActivityStore,
    fake_event_bus: FakeEventBus,
) -> None:
    """Proves: STORY-017-AC-7

    Given ``ProvidersStore`` returns a new catalog that is structurally valid
    but includes one enabled cloud provider whose api-key env-var name is
    unset, when ``reload()`` runs, then it succeeds, the new client map
    contains a client for every resolvable provider and omits the unresolved
    provider with ``MISSING_ENV``, and ``_provider_registry_reloaded`` is
    emitted exactly once more.
    """
    # Arrange
    valid_provider = make_provider_config(provider_id=_VALID_PROVIDER_ID, name="valid")
    fake_providers_store.set_providers((valid_provider,))
    registry = make_provider_registry(
        providers_store=fake_providers_store,
        client_builders=client_builders,
        gate=gate,
        event_bus=fake_event_bus,
    )
    emitted_count_after_construction = fake_event_bus.emitted_count(
        SIGNAL_PROVIDER_REGISTRY_RELOADED
    )
    unresolved_cloud_provider = make_provider_config(
        provider_id=_CLOUD_PROVIDER_ID,
        name="cloud-unresolved",
        provider_type=ProviderType.ANTHROPIC,
        base_url=None,
        api_key_raw="AN_ENV_VAR_THAT_IS_NEVER_SET",
    )
    fake_providers_store.set_providers((valid_provider, unresolved_cloud_provider))

    # Act
    registry.reload()

    # Assert
    assert registry.list_enabled() == (valid_provider, unresolved_cloud_provider)
    assert registry.get_client(_VALID_PROVIDER_ID) is not None
    with pytest.raises(ConfigurationError, match="unusable"):
        registry.get_client(_CLOUD_PROVIDER_ID)
    assert (
        fake_event_bus.emitted_count(SIGNAL_PROVIDER_REGISTRY_RELOADED)
        == emitted_count_after_construction + 1
    )
