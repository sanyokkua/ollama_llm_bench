"""Unit tests for ``_internal.test_models.TestModelsSectionWidget`` (STORY-054-AC-3, AC-5)."""

from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderTestStatus, ProviderType
from ollama_llm_bench.ui.new_benchmark._internal.test_models import TestModelsSectionWidget

_PROVIDER_A = ProviderConfig(
    provider_id="aaaaaaaa-0000-4000-8000-000000000000",
    name="Ollama Local",
    provider_type=ProviderType.OPENAI_COMPATIBLE,
    enabled=True,
    default_models=("llama3", "nomic-embed-text"),
    last_probe_status=ProviderTestStatus.UNTESTED,
)
_PROVIDER_B = ProviderConfig(
    provider_id="bbbbbbbb-0000-4000-8000-000000000000",
    name="Anthropic",
    provider_type=ProviderType.ANTHROPIC,
    enabled=True,
    default_models=("gpt-4o-mini",),
    last_probe_status=ProviderTestStatus.UNTESTED,
)


def _make_widget() -> TestModelsSectionWidget:
    return TestModelsSectionWidget(
        provider_configs_source=lambda: (_PROVIDER_A, _PROVIDER_B),
        hide_embedding_models_initial=True,
        on_hide_embedding_changed=lambda _value: None,
    )


def test_toggling_a_model_adds_it_to_the_selection_store(qtbot: QtBot) -> None:
    """Proves: STORY-054-AC-3

    Given the browsed provider is A, toggling a model on adds
    (A.provider_id, model) to the selection store.
    """
    # Arrange
    widget = _make_widget()
    qtbot.addWidget(widget)
    widget._on_browsed_provider_changed(_PROVIDER_A.provider_id)
    # Act
    widget.toggle_model_for_test("llama3")
    # Assert
    assert widget.selection.contains(_PROVIDER_A.provider_id, "llama3")


def test_hide_embedding_models_filters_available_list(qtbot: QtBot) -> None:
    """Proves: STORY-054-AC-3

    With ``hide_embedding_models`` on (the default), an embedding-marker model
    name is excluded from the browsed provider's available-models list.
    """
    # Arrange
    widget = _make_widget()
    qtbot.addWidget(widget)
    # Act
    widget._on_browsed_provider_changed(_PROVIDER_A.provider_id)
    # Assert
    assert "nomic-embed-text" not in widget.available_model_names_for_test()
    assert "llama3" in widget.available_model_names_for_test()


def test_clear_all_scopes_to_browsed_provider_via_widget(qtbot: QtBot) -> None:
    """Proves: STORY-054-AC-5

    Clicking Clear All while browsing provider A removes only A's selected
    pairs; a pair already selected from provider B is untouched.
    """
    # Arrange
    widget = _make_widget()
    qtbot.addWidget(widget)
    widget._on_browsed_provider_changed(_PROVIDER_A.provider_id)
    widget.toggle_model_for_test("llama3")
    widget._on_browsed_provider_changed(_PROVIDER_B.provider_id)
    widget.toggle_model_for_test("gpt-4o-mini")
    widget._on_browsed_provider_changed(_PROVIDER_A.provider_id)
    # Act
    widget._on_clear_all_clicked()
    # Assert
    assert widget.selection.pairs == ((_PROVIDER_B.provider_id, "gpt-4o-mini"),)


def test_clearing_all_providers_drains_selection_to_empty(qtbot: QtBot) -> None:
    """Proves: STORY-054 Definition of done

    Covers: state_machine.md §3 (Test Models sub-machine)
    SomeChecked/MultiProvider -> Empty

    Given pairs are selected from two providers (MultiProvider), clicking
    Clear All while browsing each provider in turn drains the selection store
    back to zero pairs -- the fully-empty end state, not merely a
    single-provider-scoped clear.
    """
    # Arrange
    widget = _make_widget()
    qtbot.addWidget(widget)
    widget._on_browsed_provider_changed(_PROVIDER_A.provider_id)
    widget.toggle_model_for_test("llama3")
    widget._on_browsed_provider_changed(_PROVIDER_B.provider_id)
    widget.toggle_model_for_test("gpt-4o-mini")
    # Act
    widget._on_clear_all_clicked()
    widget._on_browsed_provider_changed(_PROVIDER_A.provider_id)
    widget._on_clear_all_clicked()
    # Assert
    assert widget.selection.pairs == ()
