"""Own one ``LLMClient`` per configured provider and route ``(provider_id, model_name)``
targets to the client that serves it.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§9-§10; ``docs/v3_specification/11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md``.
"""

from ollama_llm_bench.backend.provider_registry.api import (
    ChatStream,
    ClientBuilder,
    LLMClient,
    ProviderRegistry,
    make_provider_registry,
)

__all__: list[str] = [
    "ChatStream",
    "ClientBuilder",
    "LLMClient",
    "ProviderRegistry",
    "make_provider_registry",
]
