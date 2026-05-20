"""Unit tests for SettingsWidgetController."""

from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
import yaml
from PySide6.QtCore import QCoreApplication, QThreadPool
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi,
    EventBus,
    LLMProviderApi,
    ProviderConfigLoaderApi,
    ProviderRegistryApi,
)
from ollama_llm_bench.backend.core.models import (
    EmbeddingConfig,
    ProviderConfig,
    ProvidersConfig,
    ProviderType,
)
from ollama_llm_bench.backend.services.embedding_model_classifier import EmbeddingModelClassifier
from ollama_llm_bench.backend.services.embedding_service import EmbeddingService
from ollama_llm_bench.backend.services.provider_registry import ProviderNotFoundError
from ollama_llm_bench.ui.controllers.settings_widget_controller import SettingsWidgetController

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROVIDER_CONFIG = ProviderConfig(
    provider_id="ollama_local",
    label="Ollama",
    provider_type=ProviderType.OPENAI_COMPATIBLE,
    api_key="ollama",
    enabled=True,
    base_url="http://localhost:11434/v1",
)

_PROVIDERS_CONFIG = ProvidersConfig(
    providers=(_PROVIDER_CONFIG,),
    embedding=EmbeddingConfig(provider_id="ollama_local", model="bge-m3"),
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_registry(mocker: MockerFixture) -> MagicMock:
    return cast(MagicMock, mocker.Mock(spec=ProviderRegistryApi))


@pytest.fixture()
def mock_loader(mocker: MockerFixture) -> MagicMock:
    mock = cast(MagicMock, mocker.Mock(spec=ProviderConfigLoaderApi))
    mock.serialize_config.return_value = {
        "providers": [],
        "embedding": {"provider_id": "", "model": ""},
    }
    return mock


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
        embedding_classifier=EmbeddingModelClassifier(),
    )


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return (or create) a QApplication instance for the module."""
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


# ---------------------------------------------------------------------------
# TestGetProvidersConfig
# ---------------------------------------------------------------------------


class TestGetProvidersConfig:
    def test_delegates_to_registry(
        self,
        controller: SettingsWidgetController,
        mock_registry: MagicMock,
    ) -> None:
        mock_registry.get_config.return_value = _PROVIDERS_CONFIG
        result = controller.get_providers_config()
        assert result is _PROVIDERS_CONFIG
        mock_registry.get_config.assert_called_once()

    def test_returns_none_when_registry_returns_none(
        self,
        controller: SettingsWidgetController,
        mock_registry: MagicMock,
    ) -> None:
        mock_registry.get_config.return_value = None
        assert controller.get_providers_config() is None


# ---------------------------------------------------------------------------
# TestReloadProviders
# ---------------------------------------------------------------------------


class TestReloadProviders:
    def test_calls_registry_reload(
        self,
        controller: SettingsWidgetController,
        mock_registry: MagicMock,
    ) -> None:
        controller.reload_providers()
        assert mock_registry.reload.call_count == 1

    def test_swallows_exception_from_reload(
        self,
        controller: SettingsWidgetController,
        mock_registry: MagicMock,
    ) -> None:
        mock_registry.reload.side_effect = RuntimeError("bang")
        controller.reload_providers()  # must not raise


# ---------------------------------------------------------------------------
# TestLoadProvidersYaml
# ---------------------------------------------------------------------------


class TestLoadProvidersYaml:
    def test_returns_true_on_success(
        self,
        controller: SettingsWidgetController,
        mock_loader: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_loader.load.return_value = _PROVIDERS_CONFIG
        assert controller.load_providers_yaml(tmp_path / "p.yaml") is True

    def test_calls_registry_reload_after_successful_load(
        self,
        controller: SettingsWidgetController,
        mock_loader: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_loader.load.return_value = _PROVIDERS_CONFIG
        controller.load_providers_yaml(tmp_path / "p.yaml")
        mock_registry.reload.assert_called_once()

    def test_returns_false_on_value_error(
        self,
        controller: SettingsWidgetController,
        mock_loader: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_loader.load.side_effect = ValueError("bad yaml")
        assert controller.load_providers_yaml(tmp_path / "p.yaml") is False

    def test_returns_false_on_os_error(
        self,
        controller: SettingsWidgetController,
        mock_loader: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_loader.load.side_effect = OSError("no file")
        assert controller.load_providers_yaml(tmp_path / "p.yaml") is False

    def test_does_not_call_reload_on_failure(
        self,
        controller: SettingsWidgetController,
        mock_loader: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_loader.load.side_effect = ValueError("bad yaml")
        controller.load_providers_yaml(tmp_path / "p.yaml")
        mock_registry.reload.assert_not_called()


# ---------------------------------------------------------------------------
# TestSaveProvidersYaml
# ---------------------------------------------------------------------------


class TestSaveProvidersYaml:
    def test_returns_true_and_writes_file(
        self,
        controller: SettingsWidgetController,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "out.yaml"
        assert controller.save_providers_yaml(out, _PROVIDERS_CONFIG) is True
        assert out.exists()

    def test_written_yaml_is_valid(
        self,
        controller: SettingsWidgetController,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "out.yaml"
        controller.save_providers_yaml(out, _PROVIDERS_CONFIG)
        data = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert "providers" in data
        assert "embedding" in data

    def test_returns_false_on_os_error(
        self,
        controller: SettingsWidgetController,
        mocker: MockerFixture,
        tmp_path: Path,
    ) -> None:
        mocker.patch("pathlib.Path.write_text", side_effect=OSError("disk full"))
        out = tmp_path / "out.yaml"
        assert controller.save_providers_yaml(out, _PROVIDERS_CONFIG) is False


# ---------------------------------------------------------------------------
# TestGetSetSetting
# ---------------------------------------------------------------------------


class TestGetSetSetting:
    def test_get_setting_delegates(
        self,
        controller: SettingsWidgetController,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.get.return_value = "dark"
        assert controller.get_setting("ui.theme") == "dark"
        mock_settings.get.assert_called_once_with("ui.theme")

    def test_set_setting_delegates(
        self,
        controller: SettingsWidgetController,
        mock_settings: MagicMock,
    ) -> None:
        controller.set_setting("ui.theme", "light")
        mock_settings.set.assert_called_once_with("ui.theme", "light")

    def test_get_setting_bool_delegates(
        self,
        controller: SettingsWidgetController,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.get_bool.return_value = True
        result = controller.get_setting_bool("feature.cosine_enabled", default=False)
        assert result is True
        mock_settings.get_bool.assert_called_once_with("feature.cosine_enabled", False)

    def test_get_setting_int_delegates(
        self,
        controller: SettingsWidgetController,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.get_int.return_value = 10000
        result = controller.get_setting_int("ui.log_max_lines", default=5000)
        assert result == 10000
        mock_settings.get_int.assert_called_once_with("ui.log_max_lines", 5000)


# ---------------------------------------------------------------------------
# TestProviderConnectionTest
# ---------------------------------------------------------------------------


class TestProviderConnectionTest:
    def test_calls_on_result_false_when_provider_not_found(
        self,
        controller: SettingsWidgetController,
        mock_registry: MagicMock,
    ) -> None:
        mock_registry.get_provider.side_effect = ProviderNotFoundError("not found")
        results: list[tuple[bool, int]] = []
        controller.test_provider_connection("missing", lambda ok, n, msg: results.append((ok, n)))
        assert results == [(False, 0)]

    def test_callback_fires_with_true_when_models_returned(
        self,
        controller: SettingsWidgetController,
        mock_registry: MagicMock,
        mocker: MockerFixture,
        qapp: QApplication,
    ) -> None:
        mock_provider = mocker.Mock(spec=LLMProviderApi)
        mock_provider.get_available_models.return_value = ["model-a", "model-b"]
        mock_registry.get_provider.return_value = mock_provider
        mock_registry.get_config.return_value = None

        results: list[tuple[bool, int]] = []
        controller.test_provider_connection("any_id", lambda ok, n, msg: results.append((ok, n)))

        QThreadPool.globalInstance().waitForDone(2000)
        QCoreApplication.processEvents()

        assert results == [(True, 2)]

    def test_callback_fires_with_false_when_exception_raised(
        self,
        controller: SettingsWidgetController,
        mock_registry: MagicMock,
        mocker: MockerFixture,
        qapp: QApplication,
    ) -> None:
        mock_provider = mocker.Mock(spec=LLMProviderApi)
        mock_provider.get_available_models.side_effect = RuntimeError("timeout")
        mock_registry.get_provider.return_value = mock_provider
        mock_registry.get_config.return_value = None

        results: list[tuple[bool, int]] = []
        controller.test_provider_connection("any_id", lambda ok, n, msg: results.append((ok, n)))

        QThreadPool.globalInstance().waitForDone(2000)
        QCoreApplication.processEvents()

        assert results == [(False, 0)]

    def test_pending_signals_cleaned_up_after_callback(
        self,
        controller: SettingsWidgetController,
        mock_registry: MagicMock,
        mocker: MockerFixture,
        qapp: QApplication,
    ) -> None:
        mock_provider = mocker.Mock(spec=LLMProviderApi)
        mock_provider.get_available_models.return_value = []
        mock_registry.get_provider.return_value = mock_provider
        mock_registry.get_config.return_value = None

        controller.test_provider_connection("any_id", lambda ok, n, msg: None)

        QThreadPool.globalInstance().waitForDone(2000)
        QCoreApplication.processEvents()

        assert controller._pending_signals == []


# ---------------------------------------------------------------------------
# TestIsEmbeddingModel
# ---------------------------------------------------------------------------


class TestIsEmbeddingModel:
    def test_is_embedding_model_delegates_to_classifier(
        self,
        controller: SettingsWidgetController,
    ) -> None:
        """is_embedding_model must return True for embedding names and False for others."""
        assert controller.is_embedding_model("bge-m3") is True
        assert controller.is_embedding_model("nomic-embed-text") is True
        assert controller.is_embedding_model("llama3") is False


# ---------------------------------------------------------------------------
# TestSubscribeToProviderRegistryReloaded
# ---------------------------------------------------------------------------


class TestSubscribeToProviderRegistryReloaded:
    def test_subscribe_wires_event_bus(
        self,
        controller: SettingsWidgetController,
        mock_event_bus: MagicMock,
    ) -> None:
        """subscribe_to_provider_registry_reloaded must call the event bus subscribe method."""
        callback_called: list[bool] = []

        def callback() -> None:
            callback_called.append(True)

        controller.subscribe_to_provider_registry_reloaded(callback)

        mock_event_bus.subscribe_to_provider_registry_reloaded.assert_called_once()
