"""Public surface: the OpenAI-compatible ``LLMClient`` factory.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md``, ``docs/v3_specification/08_Cross_Cutting/
08-E_interfaces_contracts.md`` §10.
"""

import icontract

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderType
from ollama_llm_bench.backend.provider_openai_compatible._internal.client_impl import (
    OpenAICompatibleClient,
)
from ollama_llm_bench.backend.provider_openai_compatible._internal.collaborators import (
    OpenAICompatibleClientCollaborators,
)
from ollama_llm_bench.backend.provider_openai_compatible.models import (
    OpenAICompatibleClientSettings,
)
from ollama_llm_bench.backend.provider_registry import ChatStream, LLMClient

__all__: list[str] = [
    "ChatStream",
    "LLMClient",
    "OpenAICompatibleClientCollaborators",
    "OpenAICompatibleClientSettings",
    "make_openai_client",
]


@icontract.require(
    lambda config: config.provider_type == ProviderType.OPENAI_COMPATIBLE,
    "make_openai_client only builds OPENAI_COMPATIBLE clients; the registry's "
    "client_builders map already routes by provider_type before calling this",
)
@icontract.ensure(lambda result: result is not None)
def make_openai_client(
    config: ProviderConfig,
    resolved_api_key: str,
    *,
    collaborators: OpenAICompatibleClientCollaborators,
    settings: OpenAICompatibleClientSettings | None = None,
) -> LLMClient:
    """Build the ``OPENAI_COMPATIBLE`` ``LLMClient`` for one provider (§6.9, SPEC-114).

    Structurally satisfies ``provider_registry.ClientBuilder`` — the registry
    always calls it with exactly ``(config, resolved_api_key)``; the
    keyword-only ``collaborators``/``settings`` bundles are bound by
    ``compose.py`` via ``functools.partial`` before the builder map is
    assembled. This module never imports ``backend/settings`` itself — the
    settings keys backing ``OpenAICompatibleClientSettings`` (
    ``provider.probe_timeout_ms`` etc.) are resolved by the caller, not here.

    Args:
        config: The enabled catalog entry to build a client for; must be
            ``OPENAI_COMPATIBLE``.
        resolved_api_key: The already-resolved secret value (``""`` for a
            keyless local host).
        collaborators: The injected ``Clock``/``EventBus``/
            ``InferenceActivityStore`` this client depends on.
        settings: The timeout/bound configuration bundle; defaults to the
            spec-mandated defaults (§7) when the caller supplies none.

    Returns:
        A constructed ``LLMClient`` satisfying the canonical Protocol.
    """
    return OpenAICompatibleClient(
        config=config,
        resolved_api_key=resolved_api_key,
        collaborators=collaborators,
        settings=settings if settings is not None else OpenAICompatibleClientSettings(),
    )
