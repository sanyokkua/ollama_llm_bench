"""Integration tests: SqliteProviderConfigRepository full field-fidelity round-trip."""

from pathlib import Path

from ollama_llm_bench.backend.core.models import EmbeddingConfig, ProviderConfig, ProviderType
from ollama_llm_bench.backend.services.sq_lite_data_api import SqLiteDataApi
from ollama_llm_bench.backend.services.sqlite_provider_config_repository import SqliteProviderConfigRepository


def _make_data_api(tmp_path: Path) -> SqLiteDataApi:
    return SqLiteDataApi(tmp_path / "test.sqlite")


def _make_repo(data_api: SqLiteDataApi) -> SqliteProviderConfigRepository:
    return SqliteProviderConfigRepository(data_api=data_api)


def _reload_repo(tmp_path: Path) -> SqliteProviderConfigRepository:
    """Open a fresh repository instance against the same DB file."""
    return _make_repo(_make_data_api(tmp_path))


class TestProviderRoundTrip:
    def test_all_core_fields_survive_save_and_reload(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        provider = ProviderConfig(
            provider_id="test_p1",
            label="Test Provider",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            api_key="sk-test",
            api_key_raw="sk-test",
            enabled=True,
            base_url="http://localhost:11434/v1",
            default_models=("model-a", "model-b"),
            azure_deployment=None,
            azure_api_version=None,
        )
        repo.save(provider)

        loaded = _reload_repo(tmp_path).load_all()[0]

        assert loaded.provider_id == provider.provider_id
        assert loaded.label == provider.label
        assert loaded.provider_type == provider.provider_type
        assert loaded.api_key_raw == provider.api_key_raw
        assert loaded.enabled == provider.enabled
        assert loaded.base_url == provider.base_url
        assert loaded.default_models == provider.default_models
        assert loaded.azure_deployment is None
        assert loaded.azure_api_version is None

    def test_none_base_url_survives_round_trip(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        provider = ProviderConfig(
            provider_id="p_no_base",
            label="No Base",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            api_key="key",
            base_url=None,
        )
        repo.save(provider)

        loaded = _reload_repo(tmp_path).load_all()[0]
        assert loaded.base_url is None

    def test_azure_fields_survive_round_trip(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        provider = ProviderConfig(
            provider_id="azure_p",
            label="Azure",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            api_key="az-key",
            azure_deployment="gpt-4-deployment",
            azure_api_version="2024-02-01",
        )
        repo.save(provider)

        loaded = _reload_repo(tmp_path).load_all()[0]
        assert loaded.azure_deployment == "gpt-4-deployment"
        assert loaded.azure_api_version == "2024-02-01"

    def test_unicode_label_and_api_key_survive_round_trip(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        provider = ProviderConfig(
            provider_id="unicode_p",
            label="Провайдер Тест 测试",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            api_key="sk-кириллица",
            api_key_raw="sk-кириллица",
        )
        repo.save(provider)

        loaded = _reload_repo(tmp_path).load_all()[0]
        assert loaded.label == "Провайдер Тест 测试"
        assert loaded.api_key_raw == "sk-кириллица"

    def test_empty_default_models_survives_round_trip(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        provider = ProviderConfig(
            provider_id="p_no_models",
            label="No Models",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            api_key="key",
            default_models=(),
        )
        repo.save(provider)

        loaded = _reload_repo(tmp_path).load_all()[0]
        assert loaded.default_models == ()

    def test_non_empty_default_models_survives_round_trip(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        models = ("llama3.2", "mistral", "qwen2.5")
        provider = ProviderConfig(
            provider_id="p_with_models",
            label="With Models",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            api_key="key",
            default_models=models,
        )
        repo.save(provider)

        loaded = _reload_repo(tmp_path).load_all()[0]
        assert loaded.default_models == models

    def test_embedding_config_survives_round_trip(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        embedding = EmbeddingConfig(provider_id="ollama_local", model="nomic-embed-text")
        repo.save_embedding_config(embedding)

        loaded = _reload_repo(tmp_path).load_embedding_config()
        assert loaded is not None
        assert loaded.provider_id == "ollama_local"
        assert loaded.model == "nomic-embed-text"

    def test_delete_removes_provider(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        repo.save(
            ProviderConfig(
                provider_id="to_delete",
                label="Del",
                provider_type=ProviderType.OPENAI_COMPATIBLE,
                api_key="k",
            )
        )
        repo.delete("to_delete")

        assert _reload_repo(tmp_path).load_all() == []

    def test_replace_all_only_retains_replacement_set(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        for pid in ("a", "b", "c"):
            repo.save(
                ProviderConfig(
                    provider_id=pid,
                    label=pid,
                    provider_type=ProviderType.OPENAI_COMPATIBLE,
                    api_key="k",
                )
            )
        replacement = [
            ProviderConfig(
                provider_id="new",
                label="New",
                provider_type=ProviderType.OPENAI_COMPATIBLE,
                api_key="k",
            )
        ]
        repo.replace_all(replacement)

        loaded_ids = {p.provider_id for p in _reload_repo(tmp_path).load_all()}
        assert loaded_ids == {"new"}

    def test_set_last_test_status_persists_and_survives_reload(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        repo.save(
            ProviderConfig(
                provider_id="p_health",
                label="Health",
                provider_type=ProviderType.OPENAI_COMPATIBLE,
                api_key="k",
            )
        )

        repo.set_last_test_status("p_health", "healthy", "2024-06-01T12:00:00+00:00", "OK")

        loaded = _reload_repo(tmp_path).load_all()[0]
        assert loaded.last_test_status == "healthy"
        assert loaded.last_test_at == "2024-06-01T12:00:00+00:00"
        assert loaded.last_test_message == "OK"

    def test_last_test_status_initially_none(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        repo.save(
            ProviderConfig(
                provider_id="p_fresh",
                label="Fresh",
                provider_type=ProviderType.OPENAI_COMPATIBLE,
                api_key="k",
            )
        )

        loaded = _reload_repo(tmp_path).load_all()[0]
        assert loaded.last_test_status is None
        assert loaded.last_test_at is None
        assert loaded.last_test_message is None
