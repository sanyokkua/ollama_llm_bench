"""Lifecycle tests for ProvidersTabWidget subscription cleanup."""

from typing import cast

import pytest
from PySide6.QtWidgets import QApplication, QWidget
from pytest_mock import MockerFixture
from shiboken6 import delete

from ollama_llm_bench.backend.core.models import ProviderRegistryReloadedEvent
from ollama_llm_bench.backend.core.ui_controllers import SettingsWidgetControllerApi
from ollama_llm_bench.ui.qt_classes.qt_event_bus import QtEventBus
from ollama_llm_bench.ui.widgets.settings.providers_tab_widget import ProvidersTabWidget


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


def _make_controller(mocker: MockerFixture) -> SettingsWidgetControllerApi:
    mock = mocker.Mock(spec=SettingsWidgetControllerApi)
    mock.get_providers_config.return_value = None
    mock.get_models_for_provider.return_value = []
    return cast(SettingsWidgetControllerApi, mock)


def test_subscribe_to_provider_registry_reloaded_passes_parent(
    qapp: QApplication,
    mocker: MockerFixture,
) -> None:
    """subscribe_to_provider_registry_reloaded must be called with parent=widget."""
    controller = _make_controller(mocker)
    widget = ProvidersTabWidget(controller=controller)

    call_args = controller.subscribe_to_provider_registry_reloaded.call_args  # type: ignore[attr-defined]
    assert call_args is not None
    assert call_args.kwargs.get("parent") is widget

    widget.deleteLater()
    QApplication.processEvents()


def test_subscribe_to_app_readiness_changed_passes_parent(
    qapp: QApplication,
    mocker: MockerFixture,
) -> None:
    """subscribe_to_app_readiness_changed must be called with parent=widget."""
    controller = _make_controller(mocker)
    widget = ProvidersTabWidget(controller=controller)

    call_args = controller.subscribe_to_app_readiness_changed.call_args  # type: ignore[attr-defined]
    assert call_args is not None
    assert call_args.kwargs.get("parent") is widget

    widget.deleteLater()
    QApplication.processEvents()


def test_subscription_auto_disconnects_on_parent_destroy(
    qapp: QApplication,
) -> None:
    """After parent destruction, _wire_auto_disconnect must remove the subscription."""
    event_bus = QtEventBus()

    # Track invocations via a mutable list (avoids bound-method complexity)
    calls: list[object] = []

    def callback(event: object) -> None:
        calls.append(event)

    # Create a plain QWidget as the parent so we control its lifecycle precisely
    parent_widget = QWidget()
    event_bus.subscribe_to_provider_registry_reloaded(callback, parent=parent_widget)

    # Emit while parent is alive — callback should fire
    event_bus.emit_provider_registry_reloaded(ProviderRegistryReloadedEvent())
    QApplication.processEvents()
    assert len(calls) == 1

    # shiboken6.delete() immediately destroys the C++ object and emits destroyed,
    # which triggers _wire_auto_disconnect to remove the subscription synchronously.
    delete(parent_widget)

    # Emit after parent destruction — callback must NOT fire again
    event_bus.emit_provider_registry_reloaded(ProviderRegistryReloadedEvent())
    QApplication.processEvents()
    assert len(calls) == 1  # still 1, no new call
