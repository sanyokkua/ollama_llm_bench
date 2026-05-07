"""Unit tests for ProviderConfigLoader."""

from pathlib import Path

import pytest
import yaml

from ollama_llm_bench.backend.core.models import (
    EmbeddingConfig,
    ProviderConfig,
    ProvidersConfig,
    ProviderType,
)
from ollama_llm_bench.backend.services.provider_config_loader import ProviderConfigLoader

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_YAML: dict[str, object] = {
    "providers": [
        {
            "id": "local",
            "label": "Local",
            "type": "openai_compatible",
            "api_key": "sk-plain123",
            "enabled": True,
            "base_url": "http://localhost:11434/v1",
        }
    ],
    "embedding": {"provider_id": "local", "model": "bge-m3"},
}


def _write_yaml(path: Path, data: dict[str, object]) -> Path:
    path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True), encoding="utf-8")
    return path


@pytest.fixture()
def loader() -> ProviderConfigLoader:
    return ProviderConfigLoader()


# ---------------------------------------------------------------------------
# api_key_raw population
# ---------------------------------------------------------------------------


def test_parse_provider_populates_api_key_raw_with_env_placeholder(
    loader: ProviderConfigLoader,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """api_key_raw must keep the ${...} placeholder; api_key resolves to empty when env var absent."""
    monkeypatch.delenv("MY_SECRET", raising=False)
    data = dict(_MINIMAL_YAML)
    data["providers"] = [
        {
            "id": "p1",
            "label": "P1",
            "type": "openai_compatible",
            "api_key": "${MY_SECRET}",
            "enabled": True,
        }
    ]
    cfg = loader.load(_write_yaml(tmp_path / "p.yaml", data))

    # Assert
    assert cfg.providers[0].api_key_raw == "${MY_SECRET}"
    assert cfg.providers[0].api_key == ""


def test_parse_provider_populates_api_key_raw_with_plain_value(
    loader: ProviderConfigLoader,
    tmp_path: Path,
) -> None:
    """Plain api_key values must be stored verbatim in both api_key_raw and api_key."""
    cfg = loader.load(_write_yaml(tmp_path / "p.yaml", _MINIMAL_YAML))

    # Assert
    assert cfg.providers[0].api_key_raw == "sk-plain123"
    assert cfg.providers[0].api_key == "sk-plain123"


# ---------------------------------------------------------------------------
# Azure fields
# ---------------------------------------------------------------------------


def test_parse_provider_reads_azure_deployment(
    loader: ProviderConfigLoader,
    tmp_path: Path,
) -> None:
    data = dict(_MINIMAL_YAML)
    data["providers"] = [
        {
            "id": "az",
            "label": "Azure",
            "type": "openai_compatible",
            "api_key": "sk-az",
            "enabled": True,
            "azure_deployment": "my-deploy",
        }
    ]
    cfg = loader.load(_write_yaml(tmp_path / "p.yaml", data))

    assert cfg.providers[0].azure_deployment == "my-deploy"


def test_parse_provider_reads_azure_api_version(
    loader: ProviderConfigLoader,
    tmp_path: Path,
) -> None:
    data = dict(_MINIMAL_YAML)
    data["providers"] = [
        {
            "id": "az",
            "label": "Azure",
            "type": "openai_compatible",
            "api_key": "sk-az",
            "enabled": True,
            "azure_api_version": "2024-02-15-preview",
        }
    ]
    cfg = loader.load(_write_yaml(tmp_path / "p.yaml", data))

    assert cfg.providers[0].azure_api_version == "2024-02-15-preview"


def test_parse_provider_azure_fields_default_to_none(
    loader: ProviderConfigLoader,
    tmp_path: Path,
) -> None:
    """When azure_deployment and azure_api_version are absent they must be None."""
    cfg = loader.load(_write_yaml(tmp_path / "p.yaml", _MINIMAL_YAML))

    assert cfg.providers[0].azure_deployment is None
    assert cfg.providers[0].azure_api_version is None


# ---------------------------------------------------------------------------
# serialize_config — api_key_raw vs resolved
# ---------------------------------------------------------------------------


def test_serialize_config_uses_api_key_raw_not_resolved(
    loader: ProviderConfigLoader,
) -> None:
    """serialize_config must write api_key_raw; the resolved (empty) api_key must not appear."""
    config = ProvidersConfig(
        providers=(
            ProviderConfig(
                provider_id="p1",
                label="P1",
                provider_type=ProviderType.OPENAI_COMPATIBLE,
                api_key="",
                api_key_raw="${MY_KEY}",
                enabled=True,
            ),
        ),
        embedding=EmbeddingConfig(provider_id="p1", model="bge-m3"),
    )

    raw = loader.serialize_config(config)

    serialized_key = raw["providers"][0]["api_key"]  # type: ignore[index]
    assert serialized_key == "${MY_KEY}"


def test_serialize_config_includes_azure_fields_when_set(
    loader: ProviderConfigLoader,
) -> None:
    config = ProvidersConfig(
        providers=(
            ProviderConfig(
                provider_id="az",
                label="Azure",
                provider_type=ProviderType.OPENAI_COMPATIBLE,
                api_key="sk",
                api_key_raw="sk",
                enabled=True,
                azure_deployment="my-deploy",
                azure_api_version="2024-01",
            ),
        ),
        embedding=EmbeddingConfig(provider_id="az", model="bge-m3"),
    )

    raw = loader.serialize_config(config)

    entry = raw["providers"][0]  # type: ignore[index]
    assert entry["azure_deployment"] == "my-deploy"
    assert entry["azure_api_version"] == "2024-01"


def test_serialize_config_omits_azure_fields_when_none(
    loader: ProviderConfigLoader,
) -> None:
    config = ProvidersConfig(
        providers=(
            ProviderConfig(
                provider_id="local",
                label="Local",
                provider_type=ProviderType.OPENAI_COMPATIBLE,
                api_key="ollama",
                api_key_raw="ollama",
                enabled=True,
            ),
        ),
        embedding=EmbeddingConfig(provider_id="local", model="bge-m3"),
    )

    raw = loader.serialize_config(config)

    entry = raw["providers"][0]  # type: ignore[index]
    assert "azure_deployment" not in entry
    assert "azure_api_version" not in entry


# ---------------------------------------------------------------------------
# Round-trip: env var placeholder survives save → reload
# ---------------------------------------------------------------------------


def test_round_trip_preserves_env_var_placeholder(
    loader: ProviderConfigLoader,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write YAML with ${MY_KEY}, load it, serialize it back — placeholder must survive."""
    monkeypatch.delenv("MY_KEY", raising=False)
    data = dict(_MINIMAL_YAML)
    data["providers"] = [
        {
            "id": "p1",
            "label": "P1",
            "type": "openai_compatible",
            "api_key": "${MY_KEY}",
            "enabled": True,
        }
    ]
    yaml_path = _write_yaml(tmp_path / "p.yaml", data)
    loaded_config = loader.load(yaml_path)

    serialized = loader.serialize_config(loaded_config)

    serialized_key = serialized["providers"][0]["api_key"]  # type: ignore[index]
    assert serialized_key == "${MY_KEY}"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_load_raises_value_error_when_providers_list_is_empty(
    loader: ProviderConfigLoader,
    tmp_path: Path,
) -> None:
    data: dict[str, object] = {"providers": [], "embedding": {"provider_id": "x", "model": "y"}}
    yaml_path = _write_yaml(tmp_path / "p.yaml", data)

    with pytest.raises(ValueError, match="at least one provider"):
        loader.load(yaml_path)


def test_load_raises_value_error_when_providers_key_missing(
    loader: ProviderConfigLoader,
    tmp_path: Path,
) -> None:
    data: dict[str, object] = {"embedding": {"provider_id": "x", "model": "y"}}
    yaml_path = _write_yaml(tmp_path / "p.yaml", data)

    with pytest.raises(ValueError):
        loader.load(yaml_path)


def test_load_raises_os_error_when_file_missing(
    loader: ProviderConfigLoader,
    tmp_path: Path,
) -> None:
    with pytest.raises(OSError):
        loader.load(tmp_path / "nonexistent.yaml")


def test_load_skips_provider_without_id(
    loader: ProviderConfigLoader,
    tmp_path: Path,
) -> None:
    """Provider entry missing 'id' must be silently skipped; other entries load normally."""
    data = dict(_MINIMAL_YAML)
    data["providers"] = [
        {"label": "NoId", "type": "openai_compatible", "api_key": "sk", "enabled": True},
        {
            "id": "good",
            "label": "Good",
            "type": "openai_compatible",
            "api_key": "sk",
            "enabled": True,
        },
    ]
    cfg = loader.load(_write_yaml(tmp_path / "p.yaml", data))

    assert len(cfg.providers) == 1
    assert cfg.providers[0].provider_id == "good"


def test_load_skips_provider_with_unknown_type(
    loader: ProviderConfigLoader,
    tmp_path: Path,
) -> None:
    """Provider entry with an unknown type must be skipped."""
    data = dict(_MINIMAL_YAML)
    data["providers"] = [
        {
            "id": "bad_type",
            "label": "Bad",
            "type": "unknown_llm",
            "api_key": "sk",
            "enabled": True,
        },
        {
            "id": "good",
            "label": "Good",
            "type": "openai_compatible",
            "api_key": "sk",
            "enabled": True,
        },
    ]
    cfg = loader.load(_write_yaml(tmp_path / "p.yaml", data))

    assert len(cfg.providers) == 1
    assert cfg.providers[0].provider_id == "good"


def test_get_enabled_providers_filters_disabled(
    loader: ProviderConfigLoader,
    tmp_path: Path,
) -> None:
    data = dict(_MINIMAL_YAML)
    data["providers"] = [
        {
            "id": "enabled_p",
            "label": "On",
            "type": "openai_compatible",
            "api_key": "sk",
            "enabled": True,
        },
        {
            "id": "disabled_p",
            "label": "Off",
            "type": "openai_compatible",
            "api_key": "sk",
            "enabled": False,
        },
    ]
    cfg = loader.load(_write_yaml(tmp_path / "p.yaml", data))

    result = loader.get_enabled_providers(cfg)

    assert len(result) == 1
    assert result[0].provider_id == "enabled_p"


def test_embedding_defaults_used_when_block_absent(
    loader: ProviderConfigLoader,
    tmp_path: Path,
) -> None:
    """When 'embedding' block is absent the defaults provider_id='ollama_local', model='bge-m3' apply."""
    data: dict[str, object] = {"providers": [_MINIMAL_YAML["providers"][0]]}  # type: ignore[index]
    cfg = loader.load(_write_yaml(tmp_path / "p.yaml", data))

    assert cfg.embedding.provider_id == "ollama_local"
    assert cfg.embedding.model == "bge-m3"


# ---------------------------------------------------------------------------
# Anthropic and Gemini base_url handling
# ---------------------------------------------------------------------------

_EMBEDDING_BLOCK: dict[str, object] = {"provider_id": "local", "model": "bge-m3"}


def _anthropic_provider_entry(**kwargs: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "local",
        "label": "Local",
        "type": "anthropic",
        "api_key": "key",
        "enabled": True,
    }
    base.update(kwargs)
    return base


def test_yaml_anthropic_with_base_url_preserves_value(
    loader: ProviderConfigLoader,
    tmp_path: Path,
) -> None:
    data: dict[str, object] = {
        "providers": [_anthropic_provider_entry(base_url="https://proxy.example.com")],
        "embedding": _EMBEDDING_BLOCK,
    }
    cfg = loader.load(_write_yaml(tmp_path / "p.yaml", data))

    assert cfg.providers[0].base_url == "https://proxy.example.com"


def test_yaml_anthropic_without_base_url_is_none(
    loader: ProviderConfigLoader,
    tmp_path: Path,
) -> None:
    data: dict[str, object] = {
        "providers": [_anthropic_provider_entry()],
        "embedding": _EMBEDDING_BLOCK,
    }
    cfg = loader.load(_write_yaml(tmp_path / "p.yaml", data))

    assert cfg.providers[0].base_url is None


def test_env_var_resolved_in_anthropic_base_url(
    loader: ProviderConfigLoader,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_PROXY", "https://x.example.com")
    data: dict[str, object] = {
        "providers": [_anthropic_provider_entry(base_url="${ANTHROPIC_PROXY}")],
        "embedding": _EMBEDDING_BLOCK,
    }
    cfg = loader.load(_write_yaml(tmp_path / "p.yaml", data))

    assert cfg.providers[0].base_url == "https://x.example.com"
