"""Secret resolution, structural validation, and single-client construction.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md``
§6.2 (building a client from a provider configuration) and §6.3 (secret resolution).
"""

from collections.abc import Mapping
import os

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderType
from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.provider_registry.protocols import ClientBuilder, LLMClient

__all__: list[str] = [
    "build_one",
    "resolve_secret",
    "validate_structure",
]

_AZURE_FIELD_COUNT = 3


def resolve_secret(provider: ProviderConfig) -> str | None:
    """Resolve a provider's api-key env-var name to its live value (§6.3).

    Args:
        provider: The catalog entry whose ``api_key_raw`` names the
            environment variable to read (or is empty for a keyless local
            provider).

    Returns:
        The resolved secret value (``""`` is a valid resolved value for a
        keyless ``OPENAI_COMPATIBLE`` local provider), or ``None`` when
        resolution fails — an empty ``api_key_raw`` for ``ANTHROPIC``/
        ``GEMINI``, or a named variable that is unset/empty.
    """
    name = provider.api_key_raw or ""
    if not name:
        if provider.provider_type is ProviderType.OPENAI_COMPATIBLE:
            return ""
        return None
    value = os.environ.get(name, "")
    return value if value else None


def validate_structure(provider: ProviderConfig) -> None:
    """Check a provider configuration is structurally complete (§6.2 step 2).

    Args:
        provider: The catalog entry to validate. Only ``OPENAI_COMPATIBLE``
            configurations carry a structural rule; ``ANTHROPIC``/``GEMINI``
            have none beyond the secret-resolution check already performed by
            ``resolve_secret``.

    Raises:
        ConfigurationError: The provider is ``OPENAI_COMPATIBLE`` with some
            but not all three Azure fields set, or with none of the Azure
            fields set and an empty ``base_url``.
    """
    if provider.provider_type is not ProviderType.OPENAI_COMPATIBLE:
        return
    azure_fields = (
        provider.azure_endpoint_raw,
        provider.azure_deployment_raw,
        provider.azure_api_version_raw,
    )
    set_count = sum(1 for field in azure_fields if field)
    if set_count == _AZURE_FIELD_COUNT:
        return
    if set_count > 0:
        raise ConfigurationError(message=f"provider {provider.name!r}: partial Azure config")
    if not provider.base_url:
        raise ConfigurationError(message=f"provider {provider.name!r}: no base_url")


def build_one(
    provider: ProviderConfig, *, client_builders: Mapping[ProviderType, ClientBuilder]
) -> LLMClient | None:
    """Build one enabled provider's client, or omit it for an unresolved secret.

    Ordering is load-bearing (§6.2/§6.3): the secret is resolved first so an
    unresolved-secret provider short-circuits as a non-error ``None`` before
    any structural check runs; only once a secret resolves does structural
    validation run, keeping the two failure modes — omit vs. structural error
    — in disjoint code paths.

    Args:
        provider: The enabled catalog entry to build a client for.
        client_builders: The per-``ProviderType`` constructor callables wired
            by ``compose.py`` from the concrete adapter factories.

    Returns:
        The constructed client, or ``None`` when the api-key env-var name is
        unset/empty (``MISSING_ENV`` — not a reload failure).

    Raises:
        ConfigurationError: The provider configuration is structurally
            invalid for its ``provider_type``.
    """
    resolved = resolve_secret(provider)
    if resolved is None:
        return None
    validate_structure(provider)
    return client_builders[provider.provider_type](provider, resolved)
