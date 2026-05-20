"""Unit tests for app_context provider path behaviour after YAML-seed removal."""

from pathlib import Path

from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import EventBus, ProviderConfigLoaderApi, ProviderRegistryApi
from ollama_llm_bench.backend.core.models import EmbeddingConfig, ProviderConfig, ProvidersConfig, ProviderType
from ollama_llm_bench.backend.services.app_settings_service import AppSettingsService
from ollama_llm_bench.backend.services.embedding_model_classifier import EmbeddingModelClassifier
from ollama_llm_bench.backend.services.embedding_service import EmbeddingService
from ollama_llm_bench.ui.controllers.settings_widget_controller import SettingsWidgetController


class TestSaveWritesToUserDataPath:
    def test_save_writes_yaml_to_standard_path(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """save_providers_config_to_standard_path writes YAML to providers_yaml_path."""
        providers_yaml_path = tmp_path / "providers.yaml"

        mock_registry = mocker.Mock(spec=ProviderRegistryApi)
        mock_config_loader = mocker.Mock(spec=ProviderConfigLoaderApi)
        mock_config_loader.serialize_config.return_value = {
            "providers": [{"id": "test-ollama", "label": "Test Ollama"}],
            "embedding": {"provider_id": "test-ollama", "model": "nomic-embed-text"},
        }
        mock_app_settings = mocker.Mock(spec=AppSettingsService)
        mock_embedding_service = mocker.Mock(spec=EmbeddingService)
        mock_event_bus = mocker.Mock(spec=EventBus)
        mock_repo = mocker.Mock()
        mock_repo.load_all.return_value = []

        controller = SettingsWidgetController(
            provider_registry=mock_registry,
            provider_config_loader=mock_config_loader,
            app_settings=mock_app_settings,
            providers_yaml_path=providers_yaml_path,
            embedding_service=mock_embedding_service,
            event_bus=mock_event_bus,
            embedding_classifier=EmbeddingModelClassifier(),
            config_repository=mock_repo,
        )

        provider = ProviderConfig(
            provider_id="test-ollama",
            label="Test Ollama",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            api_key="",
            enabled=True,
        )
        config = ProvidersConfig(
            providers=(provider,),
            embedding=EmbeddingConfig(provider_id="test-ollama", model="nomic-embed-text"),
        )

        ok = controller.save_providers_config_to_standard_path(config)

        assert ok is True
        assert providers_yaml_path.exists()
        written = providers_yaml_path.read_text()
        assert "test-ollama" in written

    def test_save_returns_true_even_when_yaml_path_unwritable(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """save_providers_config_to_standard_path returns True even if YAML write fails."""
        providers_yaml_path = tmp_path / "no_such_dir" / "providers.yaml"

        mock_registry = mocker.Mock(spec=ProviderRegistryApi)
        mock_config_loader = mocker.Mock(spec=ProviderConfigLoaderApi)
        mock_config_loader.serialize_config.return_value = {
            "providers": [],
            "embedding": {"provider_id": "", "model": ""},
        }
        mock_app_settings = mocker.Mock(spec=AppSettingsService)
        mock_embedding_service = mocker.Mock(spec=EmbeddingService)
        mock_event_bus = mocker.Mock(spec=EventBus)
        mock_repo = mocker.Mock()
        mock_repo.load_all.return_value = []

        controller = SettingsWidgetController(
            provider_registry=mock_registry,
            provider_config_loader=mock_config_loader,
            app_settings=mock_app_settings,
            providers_yaml_path=providers_yaml_path,
            embedding_service=mock_embedding_service,
            event_bus=mock_event_bus,
            embedding_classifier=EmbeddingModelClassifier(),
            config_repository=mock_repo,
        )

        provider = ProviderConfig(
            provider_id="p1",
            label="P1",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            api_key="",
            enabled=True,
        )
        config = ProvidersConfig(
            providers=(provider,),
            embedding=EmbeddingConfig(provider_id="p1", model=""),
        )

        # DB write succeeds (mock); YAML write fails (parent dir missing) → must still return True
        ok = controller.save_providers_config_to_standard_path(config)
        assert ok is True
