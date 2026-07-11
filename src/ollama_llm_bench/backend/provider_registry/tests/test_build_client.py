"""Table-driven client-build-outcome tests for ``build_one``.

Source of truth: ``docs/stories/story-017-provider-registry-and-llm-client-protocol.md``
STORY-017-AC-4.
"""

from enum import Enum, auto
from typing import NamedTuple

import pytest

from ollama_llm_bench.backend.domain import ProviderType
from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.provider_registry._internal.client_builder import build_one
from ollama_llm_bench.backend.provider_registry.protocols import ClientBuilder
from ollama_llm_bench.backend.provider_registry.tests.conftest import make_provider_config


class _Outcome(Enum):
    """The three disjoint outcomes a build attempt can produce (AC-4)."""

    BUILT = auto()
    STRUCTURAL_ERROR = auto()
    OMITTED = auto()


class _BuildCase(NamedTuple):
    """One row of the AC-4 build-outcome table."""

    provider_type: ProviderType
    base_url: str | None
    api_key_raw: str | None
    azure_fields: tuple[str | None, str | None, str | None]
    outcome: _Outcome


_AZURE_ALL_SET: tuple[str | None, str | None, str | None] = (
    "https://example.openai.azure.com",
    "gpt-deployment",
    "2024-06-01",
)
_AZURE_PARTIAL: tuple[str | None, str | None, str | None] = (
    "https://example.openai.azure.com",
    None,
    None,
)
_AZURE_NONE: tuple[str | None, str | None, str | None] = (None, None, None)


@pytest.mark.parametrize(
    "case",
    [
        _BuildCase(
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            base_url="http://localhost:11434/v1",
            api_key_raw="",
            azure_fields=_AZURE_NONE,
            outcome=_Outcome.BUILT,
        ),
        _BuildCase(
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            base_url=None,
            api_key_raw="",
            azure_fields=_AZURE_ALL_SET,
            outcome=_Outcome.BUILT,
        ),
        _BuildCase(
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            base_url=None,
            api_key_raw="",
            azure_fields=_AZURE_PARTIAL,
            outcome=_Outcome.STRUCTURAL_ERROR,
        ),
        _BuildCase(
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            base_url="",
            api_key_raw="",
            azure_fields=_AZURE_NONE,
            outcome=_Outcome.STRUCTURAL_ERROR,
        ),
        _BuildCase(
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            base_url="http://localhost:11434/v1",
            api_key_raw="",
            azure_fields=_AZURE_NONE,
            outcome=_Outcome.BUILT,
        ),
        _BuildCase(
            provider_type=ProviderType.ANTHROPIC,
            base_url=None,
            api_key_raw="RESOLVABLE_ANTHROPIC_KEY",
            azure_fields=_AZURE_NONE,
            outcome=_Outcome.BUILT,
        ),
        _BuildCase(
            provider_type=ProviderType.GEMINI,
            base_url=None,
            api_key_raw="",
            azure_fields=_AZURE_NONE,
            outcome=_Outcome.OMITTED,
        ),
    ],
    ids=[
        "openai_compatible_plain_base_url",
        "openai_compatible_full_azure_triple",
        "openai_compatible_partial_azure",
        "openai_compatible_empty_base_url_no_azure",
        "openai_compatible_keyless_local",
        "anthropic_resolved_key",
        "gemini_unresolved_key",
    ],
)
def test_build_outcome_per_provider_configuration(
    case: _BuildCase,
    monkeypatch: pytest.MonkeyPatch,
    client_builders: dict[ProviderType, ClientBuilder],
) -> None:
    """Proves: STORY-017-AC-4

    Each provider configuration maps to its build outcome: a plain
    ``OPENAI_COMPATIBLE`` provider with a ``base_url`` builds; a full Azure
    triple builds; a partial Azure set or an empty ``base_url``/no-Azure
    configuration raises a structural ``ConfigurationError``; a keyless local
    ``OPENAI_COMPATIBLE`` provider builds; ``ANTHROPIC``/``GEMINI`` build when
    their api-key env-var resolves and are omitted (``None``, no error) when
    it does not.
    """
    # Arrange
    monkeypatch.setenv("RESOLVABLE_ANTHROPIC_KEY", "sk-live-value")
    provider = make_provider_config(
        provider_type=case.provider_type,
        base_url=case.base_url,
        api_key_raw=case.api_key_raw,
        azure_fields=case.azure_fields,
    )

    # Act / Assert
    if case.outcome is _Outcome.BUILT:
        client = build_one(provider, client_builders=client_builders)
        assert client is not None
    elif case.outcome is _Outcome.STRUCTURAL_ERROR:
        with pytest.raises(ConfigurationError):
            build_one(provider, client_builders=client_builders)
    else:
        client = build_one(provider, client_builders=client_builders)
        assert client is None
