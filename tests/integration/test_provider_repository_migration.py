"""Integration tests for PR-S1: SqliteProviderConfigRepository + ProviderRegistry dual-path load."""

from pathlib import Path

import pytest

from ollama_llm_bench.backend.core.models import EmbeddingConfig, ProviderConfig, ProviderType
from ollama_llm_bench.backend.services.provider_config_loader import ProviderConfigLoader
from ollama_llm_bench.backend.services.provider_registry import ProviderRegistry
from ollama_llm_bench.backend.services.sq_lite_data_api import SqLiteDataApi
from ollama_llm_bench.backend.services.sqlite_provider_config_repository import SqliteProviderConfigRepository


def _make_data_api(tmp_path: Path) -> SqLiteDataApi:
    return SqLiteDataApi(tmp_path / "test.sqlite")


def _make_repo(data_api: SqLiteDataApi) -> SqliteProviderConfigRepository:
    return SqliteProviderConfigRepository(data_api=data_api)


def _make_provider(
    provider_id: str = "test_provider",
    label: str = "Test",
    api_key_raw: str = "sk-test",
    enabled: bool = True,
) -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id,
        label=label,
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        api_key=api_key_raw,
        api_key_raw=api_key_raw,
        enabled=enabled,
        base_url="http://localhost:11434/v1",
        default_models=("model-a",),
    )


def _make_embedding() -> EmbeddingConfig:
    return EmbeddingConfig(provider_id="ollama_local", model="nomic-embed-text")


class TestRepositoryEmptyDb:
    def test_count_returns_zero_on_empty_db(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        assert repo.count() == 0

    def test_load_all_returns_empty_list_on_empty_db(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        assert repo.load_all() == []

    def test_load_embedding_config_returns_none_on_empty_db(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        assert repo.load_embedding_config() is None


class TestRepositorySaveAndLoad:
    def test_save_increments_count(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        repo.save(_make_provider())
        assert repo.count() == 1

    def test_save_then_load_all_returns_provider(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        provider = _make_provider()
        repo.save(provider)
        loaded = repo.load_all()
        assert len(loaded) == 1
        assert loaded[0].provider_id == provider.provider_id
        assert loaded[0].label == provider.label
        assert loaded[0].provider_type == provider.provider_type
        assert loaded[0].enabled == provider.enabled
        assert loaded[0].base_url == provider.base_url

    def test_api_key_raw_preserved_on_roundtrip(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        provider = _make_provider(api_key_raw="${OPENAI_API_KEY}")
        repo.save(provider)
        loaded = repo.load_all()[0]
        assert loaded.api_key_raw == "${OPENAI_API_KEY}"

    def test_default_models_preserved_on_roundtrip(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        provider = _make_provider()
        repo.save(provider)
        loaded = repo.load_all()[0]
        assert loaded.default_models == ("model-a",)

    def test_save_multiple_providers(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        repo.save(_make_provider("p1", "Provider 1"))
        repo.save(_make_provider("p2", "Provider 2"))
        assert repo.count() == 2

    def test_upsert_replaces_existing_provider(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        repo.save(_make_provider("p1", label="Old Label"))
        repo.save(_make_provider("p1", label="New Label"))
        loaded = repo.load_all()
        assert len(loaded) == 1
        assert loaded[0].label == "New Label"


class TestRepositoryDelete:
    def test_delete_removes_provider(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        repo.save(_make_provider("p1"))
        repo.save(_make_provider("p2"))
        repo.delete("p1")
        remaining = repo.load_all()
        assert len(remaining) == 1
        assert remaining[0].provider_id == "p2"

    def test_delete_nonexistent_provider_is_noop(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        repo.delete("does_not_exist")
        assert repo.count() == 0


class TestRepositoryEmbeddingConfig:
    def test_save_and_load_embedding_config(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        embedding = _make_embedding()
        repo.save_embedding_config(embedding)
        loaded = repo.load_embedding_config()
        assert loaded is not None
        assert loaded.provider_id == embedding.provider_id
        assert loaded.model == embedding.model

    def test_upsert_replaces_embedding_config(self, tmp_path: Path) -> None:
        repo = _make_repo(_make_data_api(tmp_path))
        repo.save_embedding_config(EmbeddingConfig(provider_id="p1", model="model-a"))
        repo.save_embedding_config(EmbeddingConfig(provider_id="p2", model="model-b"))
        loaded = repo.load_embedding_config()
        assert loaded is not None
        assert loaded.provider_id == "p2"
        assert loaded.model == "model-b"


class TestEnvVarResolution:
    def test_env_var_resolved_on_registry_load(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_API_KEY_REPO", "resolved-secret")
        data_api = _make_data_api(tmp_path)
        repo = _make_repo(data_api)
        provider = _make_provider(api_key_raw="${TEST_API_KEY_REPO}")
        repo.save(provider)
        repo.save_embedding_config(_make_embedding())

        config_loader = ProviderConfigLoader()
        registry = ProviderRegistry(
            config_loader=config_loader,
            providers_yaml_path=tmp_path / "providers.yaml",
            config_repository=repo,
        )
        registry.load()
        config = registry.get_config()
        assert config is not None
        resolved = next(p for p in config.providers if p.provider_id == provider.provider_id)
        assert resolved.api_key == "resolved-secret"
        assert resolved.api_key_raw == "${TEST_API_KEY_REPO}"

    def test_api_key_raw_placeholder_stored_not_resolved(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_API_KEY_REPO2", "should-not-appear-in-db")
        data_api = _make_data_api(tmp_path)
        repo = _make_repo(data_api)
        provider = _make_provider(api_key_raw="${TEST_API_KEY_REPO2}")
        repo.save(provider)
        loaded = repo.load_all()[0]
        assert loaded.api_key_raw == "${TEST_API_KEY_REPO2}"
        assert loaded.api_key == "${TEST_API_KEY_REPO2}"


class TestRegistryDualPathLoad:
    def test_registry_loads_from_db_when_populated(self, tmp_path: Path) -> None:
        data_api = _make_data_api(tmp_path)
        repo = _make_repo(data_api)
        repo.save(_make_provider("db_provider", label="From DB"))
        repo.save_embedding_config(_make_embedding())

        config_loader = ProviderConfigLoader()
        registry = ProviderRegistry(
            config_loader=config_loader,
            providers_yaml_path=tmp_path / "nonexistent.yaml",
            config_repository=repo,
        )
        registry.load()
        config = registry.get_config()
        assert config is not None
        ids = [p.provider_id for p in config.providers]
        assert "db_provider" in ids

    def test_registry_seeds_db_from_yaml_when_db_empty(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "providers.yaml"
        yaml_path.write_text(
            "providers:\n"
            "  - id: yaml_provider\n"
            "    label: From YAML\n"
            "    type: openai_compatible\n"
            "    api_key: sk-yaml\n"
            "    base_url: http://localhost:11434/v1\n"
            "    enabled: true\n"
            "embedding:\n"
            "  provider_id: yaml_provider\n"
            "  model: nomic-embed-text\n",
            encoding="utf-8",
        )
        data_api = _make_data_api(tmp_path)
        repo = _make_repo(data_api)

        config_loader = ProviderConfigLoader()
        registry = ProviderRegistry(
            config_loader=config_loader,
            providers_yaml_path=yaml_path,
            config_repository=repo,
        )
        registry.load()

        assert repo.count() == 1
        db_providers = repo.load_all()
        assert db_providers[0].provider_id == "yaml_provider"

    def test_subsequent_load_uses_db_not_yaml(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "providers.yaml"
        yaml_path.write_text(
            "providers:\n"
            "  - id: yaml_provider\n"
            "    label: From YAML\n"
            "    type: openai_compatible\n"
            "    api_key: sk-yaml\n"
            "    base_url: http://localhost:11434/v1\n"
            "    enabled: true\n"
            "embedding:\n"
            "  provider_id: yaml_provider\n"
            "  model: nomic-embed-text\n",
            encoding="utf-8",
        )
        data_api = _make_data_api(tmp_path)
        repo = _make_repo(data_api)
        config_loader = ProviderConfigLoader()

        registry = ProviderRegistry(
            config_loader=config_loader,
            providers_yaml_path=yaml_path,
            config_repository=repo,
        )
        registry.load()
        assert repo.count() == 1

        # After first load, the YAML is archived (renamed to *.migrated-YYYYMMDD).
        # The registry itself handles this; no manual unlink needed.
        assert not yaml_path.exists(), "YAML should have been archived after first seed"

        registry2 = ProviderRegistry(
            config_loader=config_loader,
            providers_yaml_path=yaml_path,
            config_repository=repo,
        )
        registry2.load()
        config = registry2.get_config()
        assert config is not None
        assert any(p.provider_id == "yaml_provider" for p in config.providers)


class TestRepositoryResetToDefaults:
    def test_replace_all_replaces_existing_rows(self, tmp_path: Path) -> None:
        data_api = _make_data_api(tmp_path)
        repo = _make_repo(data_api)
        repo.save(_make_provider("old1"))
        repo.save(_make_provider("old2"))

        new_providers = [_make_provider("new1"), _make_provider("new2"), _make_provider("new3")]
        repo.replace_all(new_providers)

        result = repo.load_all()
        assert len(result) == 3
        result_ids = {p.provider_id for p in result}
        assert result_ids == {"new1", "new2", "new3"}

    def test_replace_all_with_empty_list_clears_all_rows(self, tmp_path: Path) -> None:
        data_api = _make_data_api(tmp_path)
        repo = _make_repo(data_api)
        repo.save(_make_provider("p1"))
        repo.save(_make_provider("p2"))

        repo.replace_all([])

        assert repo.count() == 0

    def test_save_embedding_config_upserts_correctly(self, tmp_path: Path) -> None:
        data_api = _make_data_api(tmp_path)
        repo = _make_repo(data_api)
        original = _make_embedding()
        repo.save_embedding_config(original)

        new_config = EmbeddingConfig(provider_id="new_provider", model="new-model")
        repo.save_embedding_config(new_config)

        loaded = repo.load_embedding_config()
        assert loaded is not None
        assert loaded.provider_id == "new_provider"
        assert loaded.model == "new-model"

    def test_set_last_test_status_persists_across_reload(self, tmp_path: Path) -> None:
        data_api = _make_data_api(tmp_path)
        repo = _make_repo(data_api)
        provider = _make_provider(provider_id="p1")
        repo.save(provider)

        repo.set_last_test_status("p1", "healthy", "2024-01-01T00:00:00+00:00", "All good")

        repo2 = _make_repo(_make_data_api(tmp_path))
        loaded = repo2.load_all()
        assert len(loaded) == 1
        cfg = loaded[0]
        assert cfg.last_test_status == "healthy"
        assert cfg.last_test_at == "2024-01-01T00:00:00+00:00"
        assert cfg.last_test_message == "All good"
