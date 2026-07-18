"""Unit tests for ``_internal.selection_store.SelectionStore`` (STORY-054)."""

from ollama_llm_bench.ui.new_benchmark._internal.selection_store import SelectionStore

_PROVIDER_A = "aaaaaaaa-0000-4000-8000-000000000000"
_PROVIDER_B = "bbbbbbbb-0000-4000-8000-000000000000"
_TWO_PROVIDERS = 2


def test_selection_preserved_across_provider_switch() -> None:
    """Proves: STORY-054-AC-3

    Given models are selected from provider A, when the browsed provider switches
    to B and a model there is also selected, then the store contains both pairs.
    """
    # Arrange
    store = SelectionStore()
    # Act
    store.add(_PROVIDER_A, "llama3")
    store.add(_PROVIDER_B, "mixtral")
    # Assert
    assert store.pairs == ((_PROVIDER_A, "llama3"), (_PROVIDER_B, "mixtral"))
    assert store.provider_count == _TWO_PROVIDERS


def test_clear_all_scopes_to_browsed_provider() -> None:
    """Proves: STORY-054-AC-5

    Given pairs are selected from two providers, when clear_provider is called for
    one of them, then only that provider's pairs are removed.
    """
    # Arrange
    store = SelectionStore()
    store.add(_PROVIDER_A, "llama3")
    store.add(_PROVIDER_A, "phi3")
    store.add(_PROVIDER_B, "mixtral")
    # Act
    store.clear_provider(_PROVIDER_A)
    # Assert
    assert store.pairs == ((_PROVIDER_B, "mixtral"),)


def test_remove_deletes_exactly_one_pair() -> None:
    """Proves: STORY-054-AC-3

    Removing one (provider, model) pair leaves every other pair untouched.
    """
    # Arrange
    store = SelectionStore()
    store.add(_PROVIDER_A, "llama3")
    store.add(_PROVIDER_A, "phi3")
    # Act
    store.remove(_PROVIDER_A, "llama3")
    # Assert
    assert store.pairs == ((_PROVIDER_A, "phi3"),)


def test_contains_reflects_current_membership() -> None:
    """Proves: STORY-054-AC-3

    contains() reports True only for a pair currently in the store.
    """
    # Arrange
    store = SelectionStore()
    store.add(_PROVIDER_A, "llama3")
    # Act / Assert
    assert store.contains(_PROVIDER_A, "llama3") is True
    assert store.contains(_PROVIDER_A, "phi3") is False
