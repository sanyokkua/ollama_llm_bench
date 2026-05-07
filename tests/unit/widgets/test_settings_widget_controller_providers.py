"""Unit tests for SettingsWidgetController — providers-tab methods.

Covers: save_providers_config_to_standard_path.
Does NOT duplicate tests from test_settings_widget_controller.py.
"""

from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi,
    EventBus,
    ProviderConfigLoaderApi,
    ProviderRegistryApi,
)
from ollama_llm_bench.backend.core.models import (
    EmbeddingConfig,
    ProviderConfig,
    ProvidersConfig,
    ProviderType,
)
from ollama_llm_bench.backend.services.embedding_service import EmbeddingService
from ollama_llm_bench.ui.controllers.settings_widget_controller import SettingsWidgetController

# ---------------------------------------------------------------------------
# Shared data
# ---------------------------------------------------------------------------

_EMBEDDING = EmbeddingConfig(provider_id="ollama_local", model="bge-m3")

_OPENAI_PROVIDER = ProviderConfig(
    provider_id="ollama_local",
    label="Ollama",
    provider_type=ProviderType.OPENAI_COMPATIBLE,
    api_key="ollama",
    api_key_raw="ollama",
    enabled=True,
    base_url="http://localhost:11434/v1",
)

_PROVIDERS_CONFIG = ProvidersConfig(
    providers=(_OPENAI_PROVIDER,),
    embedding=_EMBEDDING,
)


# ---------------------------------------------------------------------------
# QApplication fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_registry(mocker: MockerFixture) -> MagicMock:
    return cast(MagicMock, mocker.Mock(spec=ProviderRegistryApi))


@pytest.fixture()
def mock_loader(mocker: MockerFixture) -> MagicMock:
    return cast(MagicMock, mocker.Mock(spec=ProviderConfigLoaderApi))


@pytest.fixture()
def mock_settings(mocker: MockerFixture) -> MagicMock:
    return cast(MagicMock, mocker.Mock(spec=AppSettingsServiceApi))


@pytest.fixture()
def mock_embedding_service(mocker: MockerFixture) -> MagicMock:
    return cast(MagicMock, mocker.Mock(spec=EmbeddingService))


@pytest.fixture()
def mock_event_bus(mocker: MockerFixture) -> MagicMock:
    return cast(MagicMock, mocker.Mock(spec=EventBus))


@pytest.fixture()
def controller(
    mock_registry: MagicMock,
    mock_loader: MagicMock,
    mock_settings: MagicMock,
    mock_embedding_service: MagicMock,
    mock_event_bus: MagicMock,
    tmp_path: Path,
) -> SettingsWidgetController:
    return SettingsWidgetController(
        provider_registry=mock_registry,
        provider_config_loader=mock_loader,
        app_settings=mock_settings,
        providers_yaml_path=tmp_path / "providers.yaml",
        embedding_service=mock_embedding_service,
        event_bus=mock_event_bus,
    )


# ---------------------------------------------------------------------------
# TestSaveProvidersConfigToStandardPath
# ---------------------------------------------------------------------------


class TestSaveProvidersConfigToStandardPath:
    def test_returns_true_on_success(
        self,
        controller: SettingsWidgetController,
        tmp_path: Path,
        mock_registry: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """save_providers_config_to_standard_path must return True when file is writable."""
        # Arrange: providers.yaml path is inside tmp_path (writable)
        controller._providers_yaml_path = tmp_path / "providers.yaml"

        result = controller.save_providers_config_to_standard_path(_PROVIDERS_CONFIG)

        assert result is True

    def test_calls_registry_reload_on_success(
        self,
        controller: SettingsWidgetController,
        tmp_path: Path,
        mock_registry: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        controller._providers_yaml_path = tmp_path / "providers.yaml"

        controller.save_providers_config_to_standard_path(_PROVIDERS_CONFIG)

        mock_registry.reload.assert_called_once()

    def test_emits_provider_registry_reloaded_on_success(
        self,
        controller: SettingsWidgetController,
        tmp_path: Path,
        mock_registry: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        controller._providers_yaml_path = tmp_path / "providers.yaml"

        controller.save_providers_config_to_standard_path(_PROVIDERS_CONFIG)

        mock_event_bus.emit_provider_registry_reloaded.assert_called_once()

    def test_returns_false_on_oserror(
        self,
        controller: SettingsWidgetController,
        mock_event_bus: MagicMock,
    ) -> None:
        """When the path is not writable, must return False and NOT call event_bus."""
        controller._providers_yaml_path = Path("/nonexistent_dir_xyz/providers.yaml")

        result = controller.save_providers_config_to_standard_path(_PROVIDERS_CONFIG)

        assert result is False

    def test_does_not_emit_event_on_failure(
        self,
        controller: SettingsWidgetController,
        mock_event_bus: MagicMock,
    ) -> None:
        controller._providers_yaml_path = Path("/nonexistent_dir_xyz/providers.yaml")

        controller.save_providers_config_to_standard_path(_PROVIDERS_CONFIG)

        mock_event_bus.emit_provider_registry_reloaded.assert_not_called()

    def test_swallows_registry_reload_exception_and_still_emits_event(
        self,
        controller: SettingsWidgetController,
        tmp_path: Path,
        mock_registry: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Registry reload failure must not prevent event emission."""
        controller._providers_yaml_path = tmp_path / "providers.yaml"
        mock_registry.reload.side_effect = RuntimeError("reload failed")

        result = controller.save_providers_config_to_standard_path(_PROVIDERS_CONFIG)

        assert result is True
        mock_event_bus.emit_provider_registry_reloaded.assert_called_once()
