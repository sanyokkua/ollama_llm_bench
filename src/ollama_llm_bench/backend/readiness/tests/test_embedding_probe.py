"""Tests for the handshake-only embedding probe (§6.3, DD-48).

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/09_READINESS_PROBE.md``
§6.3, RP-13, RP-14.
"""

from ollama_llm_bench.backend.domain import ProviderHealth
from ollama_llm_bench.backend.errors import PersistenceError
from ollama_llm_bench.backend.readiness._internal.embedding_probe import probe_embedding
from ollama_llm_bench.backend.readiness.tests.conftest import (
    FakeReadinessEmbeddingSelection,
    FakeReadinessEmbeddingSelector,
    FakeReadinessLLMClient,
    FakeReadinessProviderRegistry,
    make_provider_config,
)

_PROVIDER_ID = "a3b8c1d2-7f04-4b8e-9c1d-2e5f0a1b3c4d"


def _reachable_health(provider_id: str) -> ProviderHealth:
    """A minimal reachable ``ProviderHealth`` row for ``provider_id``."""
    return ProviderHealth(
        provider_id=provider_id,
        reachable=True,
        discovery_supported=True,
        model_count=1,
        last_probe_ms=10,
        probed_at=0,
    )


def test_automatic_check_never_issues_model_compute() -> None:
    """Proves: STORY-016-AC-4

    Covers RP-13. A spy on the ``LLMClient`` fake asserts zero ``embed()``
    and zero ``chat()`` calls across a full handshake-only embedding probe,
    even when the selection is listed and embeddable.
    """
    # Arrange
    client = FakeReadinessLLMClient(
        health=_reachable_health(_PROVIDER_ID),
        supports_embedding=True,
        supports_discovery=True,
        models=("embed-model",),
    )
    registry = FakeReadinessProviderRegistry(
        enabled=(make_provider_config(provider_id=_PROVIDER_ID),),
        clients={_PROVIDER_ID: client},
    )
    selection = FakeReadinessEmbeddingSelection(
        provider=make_provider_config(provider_id=_PROVIDER_ID), model_name="embed-model"
    )
    selector = FakeReadinessEmbeddingSelector(selection=selection)

    # Act
    result = probe_embedding(
        selector=selector,
        registry=registry,
        batch_health=(_reachable_health(_PROVIDER_ID),),
    )

    # Assert
    assert result is True
    assert client.embed_calls == 0
    assert client.chat_calls == 0


def test_listed_but_cannot_embed_model_still_passes_handshake() -> None:
    """Proves: STORY-016-AC-4

    A selected embedding model that is listed but cannot actually embed
    (a stronger fact the handshake never checks, per DD-48) still passes
    the automatic handshake check — the probe never calls ``embed()`` to
    find out.
    """
    # Arrange
    client = FakeReadinessLLMClient(
        health=_reachable_health(_PROVIDER_ID),
        supports_embedding=True,
        supports_discovery=True,
        models=("listed-but-broken-model",),
    )
    registry = FakeReadinessProviderRegistry(
        enabled=(make_provider_config(provider_id=_PROVIDER_ID),),
        clients={_PROVIDER_ID: client},
    )
    selection = FakeReadinessEmbeddingSelection(
        provider=make_provider_config(provider_id=_PROVIDER_ID),
        model_name="listed-but-broken-model",
    )
    selector = FakeReadinessEmbeddingSelector(selection=selection)

    # Act
    result = probe_embedding(
        selector=selector,
        registry=registry,
        batch_health=(_reachable_health(_PROVIDER_ID),),
    )

    # Assert
    assert result is True


def test_no_selection_yields_false() -> None:
    """Proves: STORY-016-AC-4

    No embedding selection configured yields ``embedding_reachable = False``,
    not an error.
    """
    # Arrange
    selector = FakeReadinessEmbeddingSelector(selection=None)
    registry = FakeReadinessProviderRegistry()

    # Act
    result = probe_embedding(selector=selector, registry=registry, batch_health=())

    # Assert
    assert result is False


def test_selection_provider_unreachable_in_batch_yields_false() -> None:
    """Proves: STORY-016-AC-4

    A selection whose provider was not reachable in this same batch yields
    ``False`` without consulting the client at all.
    """
    # Arrange
    selection = FakeReadinessEmbeddingSelection(
        provider=make_provider_config(provider_id=_PROVIDER_ID), model_name="embed-model"
    )
    selector = FakeReadinessEmbeddingSelector(selection=selection)
    registry = FakeReadinessProviderRegistry()
    unreachable_health = ProviderHealth(
        provider_id=_PROVIDER_ID,
        reachable=False,
        discovery_supported=False,
        model_count=None,
        last_probe_ms=0,
        probed_at=0,
    )

    # Act
    result = probe_embedding(
        selector=selector, registry=registry, batch_health=(unreachable_health,)
    )

    # Assert
    assert result is False


def test_client_without_embedding_surface_yields_false() -> None:
    """Proves: STORY-016-AC-4

    A reachable provider whose client does not expose an embedding surface
    yields ``False``.
    """
    # Arrange
    client = FakeReadinessLLMClient(
        health=_reachable_health(_PROVIDER_ID), supports_embedding=False, supports_discovery=True
    )
    registry = FakeReadinessProviderRegistry(
        enabled=(make_provider_config(provider_id=_PROVIDER_ID),),
        clients={_PROVIDER_ID: client},
    )
    selection = FakeReadinessEmbeddingSelection(
        provider=make_provider_config(provider_id=_PROVIDER_ID), model_name="embed-model"
    )
    selector = FakeReadinessEmbeddingSelector(selection=selection)

    # Act
    result = probe_embedding(
        selector=selector, registry=registry, batch_health=(_reachable_health(_PROVIDER_ID),)
    )

    # Assert
    assert result is False


def test_discovery_supported_but_model_not_listed_yields_false() -> None:
    """Proves: STORY-016-AC-4

    When discovery is supported and the selected model is absent from the
    discovered list, the handshake yields ``False``.
    """
    # Arrange
    client = FakeReadinessLLMClient(
        health=_reachable_health(_PROVIDER_ID),
        supports_embedding=True,
        supports_discovery=True,
        models=("some-other-model",),
    )
    registry = FakeReadinessProviderRegistry(
        enabled=(make_provider_config(provider_id=_PROVIDER_ID),),
        clients={_PROVIDER_ID: client},
    )
    selection = FakeReadinessEmbeddingSelection(
        provider=make_provider_config(provider_id=_PROVIDER_ID), model_name="embed-model"
    )
    selector = FakeReadinessEmbeddingSelector(selection=selection)

    # Act
    result = probe_embedding(
        selector=selector, registry=registry, batch_health=(_reachable_health(_PROVIDER_ID),)
    )

    # Assert
    assert result is False


class _RaisingPersistenceSelector:
    """A ``ReadinessEmbeddingSelector`` double that always raises ``PersistenceError``."""

    def resolve_embedding_selection(self) -> None:
        """Simulate a storage failure while resolving the embedding selection."""
        raise PersistenceError(message="storage unavailable", context=None)


def test_persistence_error_resolving_selection_yields_false_not_raised() -> None:
    """Proves: STORY-016-AC-4

    Covers RP-14. A ``PersistenceError`` raised by
    ``resolve_embedding_selection`` is caught inside the embedding probe and
    treated as an unreachable embedding result — it never propagates out of
    ``probe_embedding``.
    """
    # Arrange
    selector = _RaisingPersistenceSelector()
    registry = FakeReadinessProviderRegistry()

    # Act
    result = probe_embedding(selector=selector, registry=registry, batch_health=())

    # Assert
    assert result is False
