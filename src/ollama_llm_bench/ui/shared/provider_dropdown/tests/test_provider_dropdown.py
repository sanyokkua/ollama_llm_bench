"""Colocated unit tests for ProviderDropdownWidget (STORY-052-AC-1, AC-2, AC-3)."""

from typing import cast

from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderType
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.ui.shared.provider_dropdown import make_provider_dropdown
from ollama_llm_bench.ui.shared.provider_dropdown._internal.view import ProviderDropdownWidget
from ollama_llm_bench.ui.shared.provider_dropdown.protocols import ProviderListSource

_PROVIDER_ID_ONE = "11111111-1111-4111-8111-111111111111"
_PROVIDER_ID_TWO = "22222222-2222-4222-8222-222222222222"
_ENABLED_PROVIDER_COUNT = 2


def _provider(*, provider_id: str, name: str) -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        name=name,
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
    )


def _make_source(
    mocker: MockerFixture, providers: tuple[ProviderConfig, ...]
) -> ProviderListSource:
    source = mocker.Mock(spec=ProviderListSource)
    source.list_enabled.return_value = providers
    return cast("ProviderListSource", source)


def test_populates_from_list_enabled_showing_names(
    qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-052-AC-1

    Given a ProviderRegistry-shaped source whose list_enabled() returns two enabled
    providers, when make_provider_dropdown(...) builds the widget, then the combo shows
    each provider's user-facing name, in order, and never its provider_id.
    """
    source = _make_source(
        mocker,
        (
            _provider(provider_id=_PROVIDER_ID_ONE, name="Ollama Local"),
            _provider(provider_id=_PROVIDER_ID_TWO, name="OpenAI Cloud"),
        ),
    )
    bus = mocker.Mock(spec=EventBus)

    widget = make_provider_dropdown(provider_source=source, event_bus=bus)

    assert isinstance(widget, ProviderDropdownWidget)
    assert widget.count() == _ENABLED_PROVIDER_COUNT
    assert widget.itemText(0) == "Ollama Local"
    assert widget.itemText(1) == "OpenAI Cloud"
    assert widget.itemData(0) == _PROVIDER_ID_ONE


def test_selection_emits_provider_changed_with_provider_id(
    qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-052-AC-2

    Given a populated provider dropdown, when the user selects a provider, then the
    widget emits provider_changed carrying the selected provider's internal provider_id.
    """
    source = _make_source(
        mocker,
        (
            _provider(provider_id=_PROVIDER_ID_ONE, name="Ollama Local"),
            _provider(provider_id=_PROVIDER_ID_TWO, name="OpenAI Cloud"),
        ),
    )
    bus = mocker.Mock(spec=EventBus)
    widget = make_provider_dropdown(provider_source=source, event_bus=bus)
    assert isinstance(widget, ProviderDropdownWidget)
    received: list[str] = []
    widget.provider_changed.connect(received.append)

    widget.setCurrentIndex(1)

    assert received == [_PROVIDER_ID_TWO]


def test_filter_restricts_visible_providers(qapp: QApplication, mocker: MockerFixture) -> None:
    """Proves: STORY-052-AC-3

    Given a filter callable passed to make_provider_dropdown(...), when the widget is
    built, then only the providers for which filter(provider) returns True appear.
    """
    source = _make_source(
        mocker,
        (
            _provider(provider_id=_PROVIDER_ID_ONE, name="Ollama Local"),
            _provider(provider_id=_PROVIDER_ID_TWO, name="OpenAI Cloud"),
        ),
    )
    bus = mocker.Mock(spec=EventBus)

    widget = make_provider_dropdown(
        provider_source=source,
        event_bus=bus,
        filter=lambda provider: provider.name == "OpenAI Cloud",
    )

    assert isinstance(widget, ProviderDropdownWidget)
    assert widget.count() == 1
    assert widget.itemText(0) == "OpenAI Cloud"
