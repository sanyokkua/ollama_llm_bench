"""Unit tests for the Reset to defaults button in ProvidersTabWidget."""

from typing import cast
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.models import (
    EmbeddingConfig,
    ProviderConfig,
    ProvidersConfig,
    ProviderType,
)
from ollama_llm_bench.backend.core.ui_controllers import SettingsWidgetControllerApi
from ollama_llm_bench.ui.widgets.settings.providers_tab_widget import ProvidersTabWidget


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


def _provider_config(*, provider_id: str = "p1", enabled: bool = True) -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        label=f"Provider {provider_id}",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        api_key="plain-key",
        api_key_raw="plain-key",
        enabled=enabled,
        base_url="http://localhost:11434/v1",
    )


def _make_controller(mocker: MockerFixture, providers: tuple[ProviderConfig, ...]) -> MagicMock:
    mock = cast(MagicMock, mocker.Mock(spec=SettingsWidgetControllerApi))
    mock.get_providers_config.return_value = ProvidersConfig(
        providers=providers,
        embedding=EmbeddingConfig(provider_id="p1", model="bge-m3"),
    )
    mock.get_models_for_provider.return_value = None
    return mock


class TestResetToDefaultsButton:
    def test_reset_calls_controller_on_yes(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """Confirming the reset dialog calls reset_providers_to_defaults on the controller."""
        config = _provider_config(provider_id="p1")
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        mocker.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes)

        tab._handle_reset_to_defaults()

        controller.reset_providers_to_defaults.assert_called_once()

    def test_reset_cancelled_does_not_call_controller(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """Cancelling the reset dialog does not call reset_providers_to_defaults."""
        config = _provider_config(provider_id="p1")
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        mocker.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel)

        tab._handle_reset_to_defaults()

        controller.reset_providers_to_defaults.assert_not_called()

    def test_reset_button_exists_in_ui(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """The reset-to-defaults button exists on the widget."""
        config = _provider_config(provider_id="p1")
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))

        assert hasattr(tab, "_reset_defaults_btn")

    def test_reset_per_row_shows_info_when_no_factory_default(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """Clicking Reset on a custom provider with no factory default shows an information dialog."""
        config = _provider_config(provider_id="custom_p1")
        controller = _make_controller(mocker, (config,))
        controller.get_default_provider_config.return_value = None
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        mock_info = mocker.patch.object(QMessageBox, "information")

        tab._on_reset_provider_requested(0)

        mock_info.assert_called_once()
        args = mock_info.call_args[0]
        assert args[1] == "No Factory Default"

    def test_reset_per_row_updates_model_when_factory_default_exists(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """Clicking Reset on a provider with a factory default updates the table model."""
        config = _provider_config(provider_id="p1")
        default_config = _provider_config(provider_id="p1")
        controller = _make_controller(mocker, (config,))
        controller.get_default_provider_config.return_value = default_config
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        mocker.patch.object(QMessageBox, "information")

        tab._on_reset_provider_requested(0)

        assert tab._is_dirty is True

    def test_reset_to_defaults_does_not_explicitly_call_populate(
        self,
        qapp: QApplication,
        mocker: MockerFixture,
    ) -> None:
        """_handle_reset_to_defaults must NOT call _populate_providers directly.
        Population is triggered exclusively via the provider_registry_reloaded event emitted
        by reset_providers_to_defaults(); direct call would cause a double-populate.
        """
        config = _provider_config(provider_id="p1")
        controller = _make_controller(mocker, (config,))
        tab = ProvidersTabWidget(controller=cast(SettingsWidgetControllerApi, controller))
        mocker.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes)
        spy = mocker.spy(tab, "_populate_providers")

        tab._handle_reset_to_defaults()

        # With a mocked controller no event fires, so _populate_providers must not be called
        # directly from _handle_reset_to_defaults itself.
        assert spy.call_count == 0
