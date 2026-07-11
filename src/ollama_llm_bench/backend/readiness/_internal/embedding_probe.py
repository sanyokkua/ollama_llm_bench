"""The handshake-only embedding probe (§6.3, DD-48).

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/09_READINESS_PROBE.md``
§6.3 (The embedding-model probe).

**Never calls ``embed()``.** This module only ever calls ``resolve_embedding_selection``,
``get_client``, the client's capability lookups (``supports_embedding``,
``supports_discovery``), and ``list_models`` — never ``embed`` and never ``chat``
(DD-48). A provider's reachability in the current batch is read from the just-computed
``ProviderHealth`` tuple, never re-probed.
"""

import structlog

from ollama_llm_bench.backend.domain import ModelName, ProviderHealth
from ollama_llm_bench.backend.errors import ConfigurationError, PersistenceError
from ollama_llm_bench.backend.readiness.protocols import (
    ReadinessEmbeddingSelection,
    ReadinessEmbeddingSelector,
    ReadinessLLMClient,
    ReadinessProviderRegistry,
)

__all__: list[str] = [
    "probe_embedding",
]

_logger = structlog.get_logger("app.readiness")


def probe_embedding(
    *,
    selector: ReadinessEmbeddingSelector,
    registry: ReadinessProviderRegistry,
    batch_health: tuple[ProviderHealth, ...],
) -> bool:
    """Run the handshake-only embedding-model probe (DD-48).

    Never calls ``embed()``: verifies only free signals — a selection
    exists, its provider is reachable in this batch, the client has an
    embedding surface, and (where discovery is supported) the selected
    model is listed.

    Args:
        selector: Resolves the live ``(provider, embedding model)``
            selection.
        registry: Looks up the live client for the selection's provider.
        batch_health: The just-computed per-provider health results from
            this same ``probe_all`` batch, consulted instead of re-probing
            the provider a second time.

    Returns:
        ``True`` when a selection exists, its provider is reachable in this
        batch, the client exposes an embedding surface, and (when discovery
        is supported) the selected model is listed. ``False`` in every
        other case, including a ``PersistenceError`` while resolving the
        selection (RP-14) — never raises.
    """
    selection = _resolve_selection_quietly(selector)
    if selection is None:
        return False
    if not _provider_reachable_in_batch(selection.provider.provider_id, batch_health):
        return False
    client = _get_client_quietly(registry, selection.provider.provider_id)
    if client is None:
        return False
    return _client_can_embed_selection(client, selection.model_name)


def _resolve_selection_quietly(
    selector: ReadinessEmbeddingSelector,
) -> ReadinessEmbeddingSelection | None:
    """Resolve the embedding selection, treating a storage failure as absent (RP-14)."""
    try:
        return selector.resolve_embedding_selection()
    except PersistenceError:
        _logger.warning("embedding_selection_resolve_failed")
        return None


def _get_client_quietly(
    registry: ReadinessProviderRegistry, provider_id: str
) -> ReadinessLLMClient | None:
    """Look up the selection's client, treating an unresolved config as absent."""
    try:
        return registry.get_client(provider_id)
    except ConfigurationError:
        return None


def _client_can_embed_selection(client: ReadinessLLMClient, model_name: ModelName) -> bool:
    """Whether the client exposes an embedding surface and lists the selected model."""
    if not client.supports_embedding():
        return False
    return not client.supports_discovery() or model_name in client.list_models()


def _provider_reachable_in_batch(
    provider_id: str, batch_health: tuple[ProviderHealth, ...]
) -> bool:
    """Whether ``provider_id``'s just-computed health in this batch is reachable."""
    return any(health.provider_id == provider_id and health.reachable for health in batch_health)
