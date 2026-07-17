"""Integration test: ProviderDropdownWidget rebuilds on a real event-bus reload signal
(STORY-052-AC-4).

Wires make_provider_dropdown to the real Qt-bound EventBus implementation
(adapters/qt_event_bus, STORY-040) and exercises the queued-delivery contract genuinely: a
mock EventBus.subscribe would call the handler synchronously and would not prove that the
widget rebuilds through the real, queued `_provider_registry_reloaded` delivery path. This
crosses a real Qt-delivery boundary, so it lives in tests/integration/ rather than the
module's colocated unit tests (testing-standard-pyqt skill; 07_TESTING_STANDARD.md layout).
"""

from typing import cast

from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.qt_event_bus import make_qt_event_bus_deliverer
from ollama_llm_bench.backend.domain import ProviderConfig, ProviderType
from ollama_llm_bench.backend.events import (
    SIGNAL_PROVIDER_REGISTRY_RELOADED,
    ProviderRegistryReloadedEvent,
)
from ollama_llm_bench.ui.shared.provider_dropdown import make_provider_dropdown
from ollama_llm_bench.ui.shared.provider_dropdown._internal.view import ProviderDropdownWidget
from ollama_llm_bench.ui.shared.provider_dropdown.protocols import ProviderListSource

_PROVIDER_ID_ONE = "11111111-1111-4111-8111-111111111111"
_PROVIDER_ID_TWO = "22222222-2222-4222-8222-222222222222"
_EXPANDED_PROVIDER_COUNT = 2


def _provider(*, provider_id: str, name: str) -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        name=name,
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        enabled=True,
    )


def test_rebuilds_items_on_provider_registry_reloaded(
    qtbot: QtBot, qapp: QApplication, mocker: MockerFixture
) -> None:
    """Proves: STORY-052-AC-4

    Given a built provider dropdown, when a _provider_registry_reloaded event is
    delivered, then the widget rebuilds its items from the updated
    ProviderRegistry.list_enabled() result.
    """
    bus = make_qt_event_bus_deliverer()
    source = mocker.Mock(spec=ProviderListSource)
    source.list_enabled.side_effect = [
        (_provider(provider_id=_PROVIDER_ID_ONE, name="Ollama Local"),),
        (
            _provider(provider_id=_PROVIDER_ID_ONE, name="Ollama Local"),
            _provider(provider_id=_PROVIDER_ID_TWO, name="OpenAI Cloud"),
        ),
    ]
    widget = make_provider_dropdown(
        provider_source=cast("ProviderListSource", source), event_bus=bus
    )
    assert isinstance(widget, ProviderDropdownWidget)
    qtbot.addWidget(widget)
    assert widget.count() == 1

    bus.emit(
        SIGNAL_PROVIDER_REGISTRY_RELOADED,
        ProviderRegistryReloadedEvent(
            provider_count=_EXPANDED_PROVIDER_COUNT,
            enabled_provider_ids=(_PROVIDER_ID_ONE, _PROVIDER_ID_TWO),
            reload_cause="test",
        ),
    )
    qtbot.waitUntil(lambda: widget.count() == _EXPANDED_PROVIDER_COUNT, timeout=1000)

    assert widget.itemText(1) == "OpenAI Cloud"
