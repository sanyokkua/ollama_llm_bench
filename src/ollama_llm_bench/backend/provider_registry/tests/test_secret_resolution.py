"""Secret-resolution and non-leakage tests for ``ProviderRegistryImpl``.

Source of truth: ``docs/stories/story-017-provider-registry-and-llm-client-protocol.md``
STORY-017-AC-5.
"""

from typing import TYPE_CHECKING

import pytest
import structlog.testing

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderType
from ollama_llm_bench.backend.provider_registry.api import make_provider_registry
from ollama_llm_bench.backend.provider_registry.tests.conftest import (
    FakeEventBus,
    FakeLLMClient,
    FakeProvidersStore,
    make_provider_config,
)
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

if TYPE_CHECKING:
    from ollama_llm_bench.backend.provider_registry.protocols import ClientBuilder

_SENTINEL_SECRET = "sk-sentinel-do-not-leak-9f8a7b6c"  # noqa: S105  # test-only sentinel value
_ENV_VAR_NAME = "PROVIDER_REGISTRY_TEST_API_KEY"


def test_resolved_key_is_used_but_never_logged_or_emitted(
    monkeypatch: pytest.MonkeyPatch,
    fake_providers_store: FakeProvidersStore,
    gate: FakeInferenceActivityStore,
    fake_event_bus: FakeEventBus,
) -> None:
    """Proves: STORY-017-AC-5

    Given the environment variable named by an enabled provider's
    ``api_key_raw`` is set to a non-empty value, when the registry builds
    that provider's client, then the variable is read and its resolved value
    is passed to the client builder, and no log record or emitted event
    contains the resolved value in cleartext.
    """
    # Arrange
    monkeypatch.setenv(_ENV_VAR_NAME, _SENTINEL_SECRET)
    provider = make_provider_config(
        provider_type=ProviderType.ANTHROPIC,
        base_url=None,
        api_key_raw=_ENV_VAR_NAME,
    )
    fake_providers_store.set_providers((provider,))
    captured_calls: list[tuple[str, str]] = []

    def _factory(built_provider: ProviderConfig, resolved_api_key: str) -> FakeLLMClient:
        captured_calls.append((built_provider.provider_id, resolved_api_key))
        return FakeLLMClient(provider=built_provider, resolved_api_key=resolved_api_key)

    builders: dict[ProviderType, ClientBuilder] = dict.fromkeys(ProviderType, _factory)

    # Act
    with structlog.testing.capture_logs() as captured_logs:
        registry = make_provider_registry(
            providers_store=fake_providers_store,
            client_builders=builders,
            gate=gate,
            event_bus=fake_event_bus,
        )
        registry.get_client(provider.provider_id)

    # Assert
    assert captured_calls == [(provider.provider_id, _SENTINEL_SECRET)]
    log_text = repr(captured_logs)
    assert _SENTINEL_SECRET not in log_text
    event_text = repr(fake_event_bus.emitted)
    assert _SENTINEL_SECRET not in event_text
