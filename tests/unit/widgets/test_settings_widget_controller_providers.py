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
    ProviderConfigRepositoryApi,
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
def mock_config_repository(mocker: MockerFixture) -> MagicMock:
    return cast(MagicMock, mocker.Mock(spec=ProviderConfigRepositoryApi))


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


@pytest.fixture()
def controller_with_repo(
    mock_registry: MagicMock,
    mock_loader: MagicMock,
    mock_settings: MagicMock,
    mock_embedding_service: MagicMock,
    mock_event_bus: MagicMock,
    mock_config_repository: MagicMock,
    tmp_path: Path,
) -> SettingsWidgetController:
    mock_loader.serialize_config.return_value = {
        "providers": [],
        "embedding": {"provider_id": "", "model": ""},
    }
    return SettingsWidgetController(
        provider_registry=mock_registry,
        provider_config_loader=mock_loader,
        app_settings=mock_settings,
        providers_yaml_path=tmp_path / "providers.yaml",
        embedding_service=mock_embedding_service,
        event_bus=mock_event_bus,
        embedding_classifier=EmbeddingModelClassifier(),
        config_repository=mock_config_repository,
    )


# ---------------------------------------------------------------------------
# TestSaveProvidersConfigToStandardPath
# ---------------------------------------------------------------------------


class TestSaveProvidersConfigToStandardPath:
    def test_returns_true_on_success(
        self,
        controller_with_repo: SettingsWidgetController,
        tmp_path: Path,
        mock_config_repository: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """save_providers_config_to_standard_path returns True when DB write succeeds."""
        mock_config_repository.load_all.return_value = []
        mock_config_repository.save.return_value = None
        mock_config_repository.save_embedding_config.return_value = None
        controller_with_repo._providers_yaml_path = tmp_path / "providers.yaml"

        result = controller_with_repo.save_providers_config_to_standard_path(_PROVIDERS_CONFIG)

        assert result is True

    def test_calls_registry_reload_on_success(
        self,
        controller_with_repo: SettingsWidgetController,
        tmp_path: Path,
        mock_config_repository: MagicMock,
        mock_registry: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        mock_config_repository.load_all.return_value = []
        mock_config_repository.save.return_value = None
        mock_config_repository.save_embedding_config.return_value = None
        controller_with_repo._providers_yaml_path = tmp_path / "providers.yaml"

        controller_with_repo.save_providers_config_to_standard_path(_PROVIDERS_CONFIG)

        mock_registry.reload.assert_called_once()

    def test_emits_provider_registry_reloaded_on_success(
        self,
        controller_with_repo: SettingsWidgetController,
        tmp_path: Path,
        mock_config_repository: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        mock_config_repository.load_all.return_value = []
        mock_config_repository.save.return_value = None
        mock_config_repository.save_embedding_config.return_value = None
        controller_with_repo._providers_yaml_path = tmp_path / "providers.yaml"

        controller_with_repo.save_providers_config_to_standard_path(_PROVIDERS_CONFIG)

        mock_event_bus.emit_provider_registry_reloaded.assert_called_once()

    def test_returns_true_even_when_yaml_unwritable(
        self,
        controller_with_repo: SettingsWidgetController,
        mock_config_repository: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """DB save success returns True even when YAML backup path is not writable."""
        mock_config_repository.load_all.return_value = []
        mock_config_repository.save.return_value = None
        mock_config_repository.save_embedding_config.return_value = None
        controller_with_repo._providers_yaml_path = Path("/nonexistent_dir_xyz/providers.yaml")

        result = controller_with_repo.save_providers_config_to_standard_path(_PROVIDERS_CONFIG)

        assert result is True

    def test_emits_event_even_when_yaml_unwritable(
        self,
        controller_with_repo: SettingsWidgetController,
        mock_config_repository: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Event is emitted regardless of YAML write success — DB is the source of truth."""
        mock_config_repository.load_all.return_value = []
        mock_config_repository.save.return_value = None
        mock_config_repository.save_embedding_config.return_value = None
        controller_with_repo._providers_yaml_path = Path("/nonexistent_dir_xyz/providers.yaml")

        controller_with_repo.save_providers_config_to_standard_path(_PROVIDERS_CONFIG)

        mock_event_bus.emit_provider_registry_reloaded.assert_called_once()

    def test_swallows_registry_reload_exception_and_still_emits_event(
        self,
        controller_with_repo: SettingsWidgetController,
        tmp_path: Path,
        mock_registry: MagicMock,
        mock_config_repository: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """Registry reload failure must not prevent event emission."""
        mock_config_repository.load_all.return_value = []
        mock_config_repository.save.return_value = None
        mock_config_repository.save_embedding_config.return_value = None
        controller_with_repo._providers_yaml_path = tmp_path / "providers.yaml"
        mock_registry.reload.side_effect = RuntimeError("reload failed")

        result = controller_with_repo.save_providers_config_to_standard_path(_PROVIDERS_CONFIG)

        assert result is True
        mock_event_bus.emit_provider_registry_reloaded.assert_called_once()

    def test_returns_false_when_db_raises(
        self,
        controller_with_repo: SettingsWidgetController,
        mock_config_repository: MagicMock,
        tmp_path: Path,
        mock_event_bus: MagicMock,
    ) -> None:
        """When the DB repository raises, save_providers_config_to_standard_path returns False."""
        import sqlite3

        controller_with_repo._providers_yaml_path = tmp_path / "providers.yaml"
        mock_config_repository.load_all.side_effect = sqlite3.OperationalError("disk full")

        result = controller_with_repo.save_providers_config_to_standard_path(_PROVIDERS_CONFIG)

        assert result is False

    def test_returns_true_when_yaml_backup_fails_but_db_succeeds(
        self,
        controller_with_repo: SettingsWidgetController,
        mock_config_repository: MagicMock,
        mock_event_bus: MagicMock,
    ) -> None:
        """YAML backup failure is non-fatal; result reflects DB success only."""
        mock_config_repository.load_all.return_value = []
        mock_config_repository.save.return_value = None
        mock_config_repository.save_embedding_config.return_value = None
        controller_with_repo._providers_yaml_path = Path("/nonexistent_dir_xyz/providers.yaml")

        result = controller_with_repo.save_providers_config_to_standard_path(_PROVIDERS_CONFIG)

        assert result is True


# ---------------------------------------------------------------------------
# TestLoadProvidersYaml
# ---------------------------------------------------------------------------


class TestLoadProvidersYaml:
    def test_load_providers_yaml_replaces_all_in_db(
        self,
        controller_with_repo: SettingsWidgetController,
        mock_loader: MagicMock,
        mock_config_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """load_providers_yaml must write parsed config to DB via replace_all."""
        yaml_path = tmp_path / "providers.yaml"
        yaml_path.write_text("providers: []\nembedding:\n  provider_id: p1\n  model: bge-m3\n")
        mock_loader.load.return_value = _PROVIDERS_CONFIG

        result = controller_with_repo.load_providers_yaml(yaml_path)

        assert result is True
        mock_config_repository.replace_all.assert_called_once_with(list(_PROVIDERS_CONFIG.providers))

    def test_load_providers_yaml_saves_embedding_config_to_db(
        self,
        controller_with_repo: SettingsWidgetController,
        mock_loader: MagicMock,
        mock_config_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """load_providers_yaml must also save the embedding config to the DB."""
        yaml_path = tmp_path / "providers.yaml"
        yaml_path.write_text("providers: []\nembedding:\n  provider_id: p1\n  model: bge-m3\n")
        mock_loader.load.return_value = _PROVIDERS_CONFIG

        controller_with_repo.load_providers_yaml(yaml_path)

        mock_config_repository.save_embedding_config.assert_called_once_with(_PROVIDERS_CONFIG.embedding)

    def test_load_providers_yaml_returns_false_on_load_error(
        self,
        controller_with_repo: SettingsWidgetController,
        mock_loader: MagicMock,
        mock_config_repository: MagicMock,
        tmp_path: Path,
    ) -> None:
        """load_providers_yaml must return False when loader raises and not touch the DB."""
        mock_loader.load.side_effect = ValueError("bad yaml")

        result = controller_with_repo.load_providers_yaml(tmp_path / "bad.yaml")

        assert result is False
        mock_config_repository.replace_all.assert_not_called()

    def test_load_providers_yaml_reloads_registry_on_success(
        self,
        controller_with_repo: SettingsWidgetController,
        mock_loader: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """load_providers_yaml must call registry.reload() after syncing to DB."""
        yaml_path = tmp_path / "providers.yaml"
        yaml_path.write_text("")
        mock_loader.load.return_value = _PROVIDERS_CONFIG

        controller_with_repo.load_providers_yaml(yaml_path)

        mock_registry.reload.assert_called_once()


# ---------------------------------------------------------------------------
# TestSaveProvidersYaml — serialization delegation
# ---------------------------------------------------------------------------


class TestSaveProvidersYaml:
    def test_delegates_serialization_to_loader(
        self,
        controller: SettingsWidgetController,
        mock_loader: MagicMock,
        tmp_path: Path,
    ) -> None:
        """save_providers_yaml must call loader.serialize_config, not build the dict itself."""
        mock_loader.serialize_config.return_value = {
            "providers": [],
            "embedding": {"provider_id": "", "model": ""},
        }
        path = tmp_path / "providers.yaml"

        result = controller.save_providers_yaml(path, _PROVIDERS_CONFIG)

        assert result is True
        mock_loader.serialize_config.assert_called_once_with(_PROVIDERS_CONFIG)
