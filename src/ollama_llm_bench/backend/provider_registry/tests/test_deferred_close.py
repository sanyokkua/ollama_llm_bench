"""SPEC-045 deferred-close tests for ``ProviderRegistryImpl``.

Source of truth: ``docs/stories/story-017-provider-registry-and-llm-client-protocol.md``
STORY-017-AC-8.
"""

from typing import TYPE_CHECKING

import pytest

from ollama_llm_bench.backend.domain import InferenceActivity, ProviderConfig, ProviderType
from ollama_llm_bench.backend.provider_registry.api import make_provider_registry
from ollama_llm_bench.backend.provider_registry.tests.conftest import (
    FakeClock,
    FakeEventBus,
    FakeLLMClient,
    FakeProvidersStore,
    make_activity_context,
    make_provider_config,
)
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

if TYPE_CHECKING:
    from ollama_llm_bench.backend.provider_registry.protocols import ClientBuilder

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize("gate_busy_at_swap", [False, True], ids=["gate_idle", "gate_busy"])
def test_superseded_clients_close_only_when_gate_idle(
    *,
    gate_busy_at_swap: bool,
    fake_providers_store: FakeProvidersStore,
    fake_clock: FakeClock,
    fake_event_bus: FakeEventBus,
) -> None:
    """Proves: STORY-017-AC-8

    Given a successful ``reload()`` that supersedes a prior client map: when
    the single-inference gate is ``IDLE`` at swap time, every superseded
    client is closed immediately during ``reload()``; when the gate is held
    by any activity, no superseded client is closed during ``reload()`` and
    every client is closed only once the next
    ``_inference_activity_changed -> IDLE`` event fires.
    """
    # Arrange
    gate = FakeInferenceActivityStore(clock=fake_clock, event_bus=fake_event_bus)
    built_clients: list[FakeLLMClient] = []

    def _factory(provider: ProviderConfig, resolved_api_key: str) -> FakeLLMClient:
        client = FakeLLMClient(provider=provider, resolved_api_key=resolved_api_key)
        built_clients.append(client)
        return client

    builders: dict[ProviderType, ClientBuilder] = dict.fromkeys(ProviderType, _factory)
    provider = make_provider_config(provider_id=_PROVIDER_ID, name="provider")
    fake_providers_store.set_providers((provider,))
    registry = make_provider_registry(
        providers_store=fake_providers_store,
        client_builders=builders,
        gate=gate,
        event_bus=fake_event_bus,
    )
    original_client = built_clients[0]
    lease = (
        gate.try_acquire(InferenceActivity.PROVIDER_TEST, make_activity_context())
        if gate_busy_at_swap
        else None
    )
    if gate_busy_at_swap:
        assert lease is not None

    # Act
    fake_providers_store.set_providers((provider,))
    registry.reload()

    # Assert
    if not gate_busy_at_swap:
        assert original_client.closed
    else:
        assert not original_client.closed
        assert lease is not None
        gate.release(lease)
        assert original_client.closed
