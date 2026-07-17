"""Colocated unit tests for ModelDropdownWidget (STORY-052-AC-5, AC-6)."""

from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.ui.shared.model_dropdown import make_model_dropdown
from ollama_llm_bench.ui.shared.model_dropdown._internal.view import ModelDropdownWidget
from ollama_llm_bench.ui.shared.model_dropdown.protocols import ModelFetcher

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"


def test_set_provider_populates_from_list_models_with_filter(
    qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-052-AC-5

    Given a filter callable and a model_dropdown, when the consumer calls
    set_provider(provider_id), then the combo is populated from
    ProviderRegistry.get_client(provider_id).list_models(), restricted to the models for
    which filter(model) returns True.
    """
    fetcher = mocker.Mock(spec=ModelFetcher)
    fetcher.fetch_models.side_effect = lambda provider_id, *, on_success, on_error: on_success(
        provider_id, ("llama3", "mxbai-embed-large")
    )
    widget = make_model_dropdown(model_fetcher=fetcher, filter=lambda name: "embed" not in name)
    assert isinstance(widget, ModelDropdownWidget)

    widget.set_provider(_PROVIDER_ID)

    fetcher.fetch_models.assert_called_once()
    assert widget.count() == 1
    assert widget.itemText(0) == "llama3"


def test_selection_emits_model_changed_with_model_name(
    qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-052-AC-6

    Given a populated model dropdown, when the user selects a model, then the widget
    emits model_changed carrying the selected model's name.
    """
    fetcher = mocker.Mock(spec=ModelFetcher)
    fetcher.fetch_models.side_effect = lambda provider_id, *, on_success, on_error: on_success(
        provider_id, ("llama3", "mistral")
    )
    widget = make_model_dropdown(model_fetcher=fetcher)
    assert isinstance(widget, ModelDropdownWidget)
    widget.set_provider(_PROVIDER_ID)
    received: list[str] = []
    widget.model_changed.connect(received.append)

    widget.setCurrentIndex(1)

    assert received == ["mistral"]
