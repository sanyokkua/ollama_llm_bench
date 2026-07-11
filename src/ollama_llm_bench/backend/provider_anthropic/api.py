"""Public surface: the Anthropic ``LLMClient`` factory.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md``, ``docs/v3_specification/08_Cross_Cutting/
08-E_interfaces_contracts.md`` §10.
"""

import icontract

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderType
from ollama_llm_bench.backend.provider_anthropic._internal.client_impl import AnthropicClient
from ollama_llm_bench.backend.provider_anthropic._internal.collaborators import (
    AnthropicClientCollaborators,
)
from ollama_llm_bench.backend.provider_anthropic.models import AnthropicClientSettings
from ollama_llm_bench.backend.provider_registry import ChatStream, LLMClient

__all__: list[str] = [
    "AnthropicClientCollaborators",
    "AnthropicClientSettings",
    "ChatStream",
    "LLMClient",
    "make_anthropic_client",
]


@icontract.require(
    lambda config: config.provider_type == ProviderType.ANTHROPIC,
    "make_anthropic_client only builds ANTHROPIC clients; the registry's client_builders "
    "map already routes by provider_type before calling this",
)
@icontract.ensure(lambda result: result is not None)
def make_anthropic_client(
    config: ProviderConfig,
    resolved_api_key: str,
    *,
    collaborators: AnthropicClientCollaborators,
    settings: AnthropicClientSettings | None = None,
) -> LLMClient:
    """Build the ``ANTHROPIC`` ``LLMClient`` for one provider (§6.9).

    Structurally satisfies ``provider_registry.ClientBuilder`` — the registry
    always calls it with exactly ``(config, resolved_api_key)``; the
    keyword-only ``collaborators``/``settings`` bundles are bound by
    ``compose.py`` via ``functools.partial`` before the builder map is
    assembled. This module never imports ``backend/settings`` itself — the
    settings keys backing ``AnthropicClientSettings`` (
    ``provider.probe_timeout_ms`` etc.) are resolved by the caller, not here.

    Args:
        config: The enabled catalog entry to build a client for; must be
            ``ANTHROPIC``.
        resolved_api_key: The already-resolved secret value.
        collaborators: The injected ``Clock``/``EventBus``/
            ``InferenceActivityStore`` this client depends on.
        settings: The timeout/bound configuration bundle; defaults to the
            spec-mandated defaults (§7) when the caller supplies none.

    Returns:
        A constructed ``LLMClient`` satisfying the canonical Protocol.
    """
    return AnthropicClient(
        config=config,
        resolved_api_key=resolved_api_key,
        collaborators=collaborators,
        settings=settings if settings is not None else AnthropicClientSettings(),
    )
