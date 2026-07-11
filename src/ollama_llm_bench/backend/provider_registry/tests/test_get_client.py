"""Table-driven ``get_client`` outcome tests for ``ProviderRegistryImpl``.

Source of truth: ``docs/stories/story-017-provider-registry-and-llm-client-protocol.md``
STORY-017-AC-3.
"""

from typing import NamedTuple

import pytest

from ollama_llm_bench.backend.domain import ProviderType
from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.provider_registry.api import make_provider_registry
from ollama_llm_bench.backend.provider_registry.protocols import ClientBuilder
from ollama_llm_bench.backend.provider_registry.tests.conftest import (
    FakeEventBus,
    FakeProvidersStore,
    make_provider_config,
)
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

_KNOWN_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_UNKNOWN_PROVIDER_ID = "99999999-9999-4999-8999-999999999999"


class _GetClientCase(NamedTuple):
    """One row of the AC-3 ``get_client`` outcome table."""

    provider_present: bool
    enabled: bool
    api_key_raw: str
    requested_id: str
    expect_error_match: str | None


@pytest.mark.parametrize(
    "case",
    [
        _GetClientCase(
            provider_present=False,
            enabled=True,
            api_key_raw="",
            requested_id=_UNKNOWN_PROVIDER_ID,
            expect_error_match="unknown",
        ),
        _GetClientCase(
            provider_present=True,
            enabled=False,
            api_key_raw="",
            requested_id=_KNOWN_PROVIDER_ID,
            expect_error_match="disabled",
        ),
        _GetClientCase(
            provider_present=True,
            enabled=True,
            api_key_raw="",
            requested_id=_KNOWN_PROVIDER_ID,
            expect_error_match=None,
        ),
        _GetClientCase(
            provider_present=True,
            enabled=True,
            api_key_raw="MISSING_ENV_VAR_NAME",
            requested_id=_KNOWN_PROVIDER_ID,
            expect_error_match="unusable",
        ),
    ],
    ids=["not_in_catalog", "disabled", "enabled_valid_resolved", "enabled_unresolved_secret"],
)
def test_get_client_outcome_per_provider_state(
    case: _GetClientCase,
    fake_providers_store: FakeProvidersStore,
    client_builders: dict[ProviderType, ClientBuilder],
    gate: FakeInferenceActivityStore,
    fake_event_bus: FakeEventBus,
) -> None:
    """Proves: STORY-017-AC-3

    Each ``get_client(provider_id)`` outcome is determined by the provider's
    catalog state: not-in-catalog raises ``ConfigurationError`` naming
    "unknown"; in-catalog-disabled raises naming "disabled"; enabled valid
    resolved returns the live client; enabled valid with an unresolved secret
    raises naming "unusable".
    """
    # Arrange
    catalog = (
        (
            make_provider_config(
                provider_id=_KNOWN_PROVIDER_ID,
                enabled=case.enabled,
                api_key_raw=case.api_key_raw,
            ),
        )
        if case.provider_present
        else ()
    )
    fake_providers_store.set_providers(catalog)
    registry = make_provider_registry(
        providers_store=fake_providers_store,
        client_builders=client_builders,
        gate=gate,
        event_bus=fake_event_bus,
    )

    # Act / Assert
    if case.expect_error_match is None:
        client = registry.get_client(case.requested_id)
        assert client is not None
    else:
        with pytest.raises(ConfigurationError, match=case.expect_error_match):
            registry.get_client(case.requested_id)
