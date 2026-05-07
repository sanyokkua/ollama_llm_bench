"""Unit tests for ProviderRegistry — load, guard, accessor, and failure behaviour."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import ProviderConfigLoaderApi
from ollama_llm_bench.backend.core.models import (
    EmbeddingConfig,
    ProviderConfig,
    ProvidersConfig,
    ProviderType,
)
from ollama_llm_bench.backend.services.provider_registry import (
    ProviderNotFoundError,
    ProviderRegistry,
)

# ---------------------------------------------------------------------------
# Shared test fixtures / helpers
# ---------------------------------------------------------------------------

_OLLAMA_CONFIG = ProviderConfig(
    provider_id="ollama_local",
    label="Ollama",
    provider_type=ProviderType.OPENAI_COMPATIBLE,
    api_key="ollama",
    enabled=True,
    base_url="http://localhost:11434/v1",
)

_DISABLED_CONFIG = ProviderConfig(
    provider_id="disabled_provider",
    label="Disabled",
    provider_type=ProviderType.OPENAI_COMPATIBLE,
    api_key="key",
    enabled=False,
    base_url="http://localhost:9999/v1",
)

_ANTHROPIC_CONFIG = ProviderConfig(
    provider_id="anthropic_main",
    label="Anthropic",
    provider_type=ProviderType.ANTHROPIC,
    api_key="sk-ant-test",
    enabled=True,
)

_GEMINI_CONFIG = ProviderConfig(
    provider_id="gemini_main",
    label="Gemini",
    provider_type=ProviderType.GEMINI,
    api_key="AIza-test",
    enabled=True,
)

_EMBEDDING_CONFIG = EmbeddingConfig(provider_id="ollama_local", model="bge-m3")


def _make_registry(
    mocker: MockerFixture,
    *,
    providers: tuple[ProviderConfig, ...] = (_OLLAMA_CONFIG,),
    embedding: EmbeddingConfig = _EMBEDDING_CONFIG,
) -> ProviderRegistry:
    """Create a ProviderRegistry with mocked config loader and patched openai.OpenAI."""
    mock_loader = mocker.Mock(spec=ProviderConfigLoaderApi)
    mock_loader.load.return_value = ProvidersConfig(providers=providers, embedding=embedding)
    # Patch openai.OpenAI so no real connection is attempted
    mocker.patch("ollama_llm_bench.backend.services.providers.openai_compatible_provider.openai.OpenAI")
    mocker.patch("ollama_llm_bench.backend.services.providers.openai_embedding_provider.openai.OpenAI")
    registry = ProviderRegistry(
        config_loader=mock_loader,
        providers_yaml_path=Path("providers.yaml"),
    )
    return registry


# ---------------------------------------------------------------------------
# Guard — accessors called before load()
# ---------------------------------------------------------------------------


def test_get_provider_before_load_raises_runtime_error(mocker: MockerFixture) -> None:
    # Arrange
    mock_loader = mocker.Mock(spec=ProviderConfigLoaderApi)
    registry = ProviderRegistry(
        config_loader=mock_loader,
        providers_yaml_path=Path("providers.yaml"),
    )

    # Act / Assert
    with pytest.raises(RuntimeError, match="call load\\(\\) first"):
        registry.get_provider("ollama_local")


def test_get_all_providers_before_load_raises_runtime_error(mocker: MockerFixture) -> None:
    # Arrange
    mock_loader = mocker.Mock(spec=ProviderConfigLoaderApi)
    registry = ProviderRegistry(
        config_loader=mock_loader,
        providers_yaml_path=Path("providers.yaml"),
    )

    # Act / Assert
    with pytest.raises(RuntimeError, match="call load\\(\\) first"):
        registry.get_all_providers()


def test_get_enabled_providers_before_load_raises_runtime_error(mocker: MockerFixture) -> None:
    # Arrange
    mock_loader = mocker.Mock(spec=ProviderConfigLoaderApi)
    registry = ProviderRegistry(
        config_loader=mock_loader,
        providers_yaml_path=Path("providers.yaml"),
    )

    # Act / Assert
    with pytest.raises(RuntimeError, match="call load\\(\\) first"):
        registry.get_enabled_providers()


def test_get_embedding_provider_before_load_raises_runtime_error(mocker: MockerFixture) -> None:
    # Arrange
    mock_loader = mocker.Mock(spec=ProviderConfigLoaderApi)
    registry = ProviderRegistry(
        config_loader=mock_loader,
        providers_yaml_path=Path("providers.yaml"),
    )

    # Act / Assert
    with pytest.raises(RuntimeError, match="call load\\(\\) first"):
        registry.get_embedding_provider()


# ---------------------------------------------------------------------------
# load() — happy path
# ---------------------------------------------------------------------------


def test_load_builds_providers_from_config(mocker: MockerFixture) -> None:
    # Arrange
    registry = _make_registry(mocker, providers=(_OLLAMA_CONFIG,))

    # Act
    registry.load()

    # Assert
    providers = registry.get_all_providers()
    assert len(providers) == 1


def test_load_with_multiple_providers_builds_all(mocker: MockerFixture) -> None:
    # Arrange
    mocker.patch("ollama_llm_bench.backend.services.providers.anthropic_provider.anthropic.Anthropic")
    mocker.patch("ollama_llm_bench.backend.services.providers.gemini_provider.google.genai.Client")
    registry = _make_registry(
        mocker,
        providers=(_OLLAMA_CONFIG, _ANTHROPIC_CONFIG, _GEMINI_CONFIG),
        embedding=_EMBEDDING_CONFIG,
    )

    # Act
    registry.load()

    # Assert
    providers = registry.get_all_providers()
    assert len(providers) == 3


# ---------------------------------------------------------------------------
# get_provider — by ID
# ---------------------------------------------------------------------------


def test_get_provider_returns_correct_provider(mocker: MockerFixture) -> None:
    # Arrange
    registry = _make_registry(mocker, providers=(_OLLAMA_CONFIG,))
    registry.load()

    # Act
    provider = registry.get_provider("ollama_local")

    # Assert
    assert provider is not None


def test_get_provider_returns_object_with_matching_provider_id(mocker: MockerFixture) -> None:
    # Arrange
    registry = _make_registry(mocker, providers=(_OLLAMA_CONFIG,))
    registry.load()

    # Act
    provider = registry.get_provider("ollama_local")

    # Assert
    assert provider.provider_id == "ollama_local"


def test_get_provider_nonexistent_raises_provider_not_found_error(mocker: MockerFixture) -> None:
    # Arrange
    registry = _make_registry(mocker, providers=(_OLLAMA_CONFIG,))
    registry.load()

    # Act / Assert
    with pytest.raises(ProviderNotFoundError):
        registry.get_provider("nonexistent_provider")


def test_provider_not_found_error_is_key_error_subclass() -> None:
    # Assert — ProviderNotFoundError must be a KeyError subclass per interface contract
    assert issubclass(ProviderNotFoundError, KeyError)


# ---------------------------------------------------------------------------
# get_enabled_providers — filtering
# ---------------------------------------------------------------------------


def test_get_enabled_providers_filters_disabled(mocker: MockerFixture) -> None:
    # Arrange — one enabled, one disabled
    registry = _make_registry(
        mocker,
        providers=(_OLLAMA_CONFIG, _DISABLED_CONFIG),
    )
    registry.load()

    # Act
    enabled = registry.get_enabled_providers()

    # Assert — only the enabled provider is returned
    assert len(enabled) == 1


def test_get_enabled_providers_returns_enabled_id(mocker: MockerFixture) -> None:
    # Arrange
    registry = _make_registry(
        mocker,
        providers=(_OLLAMA_CONFIG, _DISABLED_CONFIG),
    )
    registry.load()

    # Act
    enabled = registry.get_enabled_providers()

    # Assert
    assert enabled[0].provider_id == "ollama_local"


def test_get_enabled_providers_all_disabled_returns_empty(mocker: MockerFixture) -> None:
    # Arrange
    disabled_only = ProviderConfig(
        provider_id="only_disabled",
        label="Disabled",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        api_key="key",
        enabled=False,
        base_url="http://localhost:9999/v1",
    )
    registry = _make_registry(
        mocker,
        providers=(disabled_only,),
        embedding=EmbeddingConfig(provider_id="only_disabled", model="bge-m3"),
    )
    registry.load()

    # Act
    enabled = registry.get_enabled_providers()

    # Assert
    assert enabled == []


# ---------------------------------------------------------------------------
# load() — failure paths
# ---------------------------------------------------------------------------


def test_load_failure_leaves_empty_providers_no_crash(mocker: MockerFixture) -> None:
    # Arrange — config loader throws on load
    mock_loader = mocker.Mock(spec=ProviderConfigLoaderApi)
    mock_loader.load.side_effect = Exception("load failed")
    registry = ProviderRegistry(
        config_loader=mock_loader,
        providers_yaml_path=Path("providers.yaml"),
    )

    # Act — must NOT raise
    registry.load()

    # Assert — registry is empty but accessible
    providers = registry.get_all_providers()
    assert providers == []


def test_load_failure_config_is_none_enabled_providers_returns_empty(
    mocker: MockerFixture,
) -> None:
    # Arrange
    mock_loader = mocker.Mock(spec=ProviderConfigLoaderApi)
    mock_loader.load.side_effect = Exception("bad yaml")
    registry = ProviderRegistry(
        config_loader=mock_loader,
        providers_yaml_path=Path("providers.yaml"),
    )
    registry.load()

    # Act
    enabled = registry.get_enabled_providers()

    # Assert
    assert enabled == []


def test_load_failure_marks_is_loaded_true(mocker: MockerFixture) -> None:
    # Arrange — even on failure, _is_loaded must be True so accessors don't raise RuntimeError
    mock_loader = mocker.Mock(spec=ProviderConfigLoaderApi)
    mock_loader.load.side_effect = Exception("bad yaml")
    registry = ProviderRegistry(
        config_loader=mock_loader,
        providers_yaml_path=Path("providers.yaml"),
    )

    # Act
    registry.load()

    # Assert — no RuntimeError; registry is accessible
    assert registry.get_all_providers() == []


def test_single_provider_build_failure_skips_that_provider(mocker: MockerFixture) -> None:
    # Arrange — patch openai.OpenAI at the top-level openai module (provider does
    # `import openai` then calls `openai.OpenAI(...)` so the correct target is
    # the attribute on the already-imported openai module object).
    mocker.patch("openai.OpenAI", side_effect=Exception("connection refused"))
    mock_loader = mocker.Mock(spec=ProviderConfigLoaderApi)
    mock_loader.load.return_value = ProvidersConfig(
        providers=(_OLLAMA_CONFIG,),
        embedding=_EMBEDDING_CONFIG,
    )
    registry = ProviderRegistry(
        config_loader=mock_loader,
        providers_yaml_path=Path("providers.yaml"),
    )

    # Act — must not raise
    registry.load()

    # Assert — the failed provider is absent; empty list, no crash
    assert registry.get_all_providers() == []


# ---------------------------------------------------------------------------
# reload()
# ---------------------------------------------------------------------------


def test_reload_replaces_providers(mocker: MockerFixture) -> None:
    # Arrange
    registry = _make_registry(mocker, providers=(_OLLAMA_CONFIG,))
    registry.load()
    assert len(registry.get_all_providers()) == 1

    # Act — reload with same config; must succeed without error
    registry.reload()

    # Assert — providers still available
    assert len(registry.get_all_providers()) == 1


def test_reload_after_failure_can_recover(mocker: MockerFixture) -> None:
    # Arrange — first load fails, second succeeds
    mock_loader = mocker.Mock(spec=ProviderConfigLoaderApi)
    mock_loader.load.side_effect = [
        Exception("first load failed"),
        ProvidersConfig(providers=(_OLLAMA_CONFIG,), embedding=_EMBEDDING_CONFIG),
    ]
    mocker.patch("ollama_llm_bench.backend.services.providers.openai_compatible_provider.openai.OpenAI")
    mocker.patch("ollama_llm_bench.backend.services.providers.openai_embedding_provider.openai.OpenAI")
    registry = ProviderRegistry(
        config_loader=mock_loader,
        providers_yaml_path=Path("providers.yaml"),
    )
    registry.load()
    assert registry.get_all_providers() == []  # first load empty

    # Act
    registry.reload()

    # Assert — second load succeeded
    assert len(registry.get_all_providers()) == 1


# ---------------------------------------------------------------------------
# get_all_providers — edge cases
# ---------------------------------------------------------------------------


def test_get_all_providers_returns_list_not_same_object(mocker: MockerFixture) -> None:
    # Arrange
    registry = _make_registry(mocker, providers=(_OLLAMA_CONFIG,))
    registry.load()

    # Act
    providers_a = registry.get_all_providers()
    providers_b = registry.get_all_providers()

    # Assert — each call returns a new list (defensive copy)
    assert providers_a is not providers_b
    assert providers_a == providers_b


def test_get_all_providers_empty_config_returns_empty(mocker: MockerFixture) -> None:
    # Arrange — no provider entries; embedding provider_id points to nothing
    registry = _make_registry(
        mocker,
        providers=(),
        embedding=EmbeddingConfig(provider_id="missing", model="bge-m3"),
    )
    registry.load()

    # Act
    providers = registry.get_all_providers()

    # Assert
    assert providers == []


# ---------------------------------------------------------------------------
# Unknown provider type — skipped with warning, no crash
# ---------------------------------------------------------------------------


def test_load_skips_provider_with_unknown_type(mocker: MockerFixture) -> None:
    # Arrange — inject a ProviderConfig whose provider_type is not in the factory
    # dispatch table.  We do this by using a real ProviderType value, then monkey-
    # patching the dispatch table so it has no entry for ANTHROPIC.
    mocker.patch.dict(
        "ollama_llm_bench.backend.services.provider_registry._PROVIDER_FACTORIES",
        {},
        clear=True,
    )
    registry = _make_registry(mocker, providers=(_OLLAMA_CONFIG,))

    # Act
    registry.load()

    # Assert — no providers built because the factory table is empty
    assert registry.get_all_providers() == []


# ---------------------------------------------------------------------------
# _resolve_embedding — non-openai_compatible embedding provider type
# ---------------------------------------------------------------------------


def test_load_skips_embedding_service_when_provider_type_not_openai_compatible(
    mocker: MockerFixture,
) -> None:
    # Arrange — embedding provider_id points to an Anthropic-typed provider
    anthropic_config = ProviderConfig(
        provider_id="anthropic_embed",
        label="Anthropic",
        provider_type=ProviderType.ANTHROPIC,
        api_key="key",
        enabled=True,
    )
    mocker.patch("ollama_llm_bench.backend.services.providers.anthropic_provider.anthropic.Anthropic")
    mock_loader = mocker.Mock(spec=ProviderConfigLoaderApi)
    mock_loader.load.return_value = ProvidersConfig(
        providers=(anthropic_config,),
        embedding=EmbeddingConfig(provider_id="anthropic_embed", model="bge-m3"),
    )
    registry = ProviderRegistry(
        config_loader=mock_loader,
        providers_yaml_path=Path("providers.yaml"),
    )

    # Act
    registry.load()

    # Assert — embedding service is None, so get_embedding_provider raises
    with pytest.raises(RuntimeError, match="Embedding provider not available"):
        registry.get_embedding_provider()


# ---------------------------------------------------------------------------
# get_embedding_provider — raises when embedding service unavailable
# ---------------------------------------------------------------------------


def test_get_embedding_provider_raises_when_embedding_provider_missing(
    mocker: MockerFixture,
) -> None:
    # Arrange — embedding config points to a provider_id that doesn't exist in providers
    registry = _make_registry(
        mocker,
        providers=(_OLLAMA_CONFIG,),
        embedding=EmbeddingConfig(provider_id="nonexistent_embed", model="bge-m3"),
    )
    registry.load()

    # Act / Assert
    with pytest.raises(RuntimeError, match="Embedding provider not available"):
        registry.get_embedding_provider()


# ---------------------------------------------------------------------------
# get_config() — returns raw ProvidersConfig or None
# ---------------------------------------------------------------------------


class TestGetConfig:
    def test_get_config_returns_none_before_load(self, mocker: MockerFixture) -> None:
        # Arrange
        registry = _make_registry(mocker)

        # Act / Assert
        assert registry.get_config() is None

    def test_get_config_returns_config_after_successful_load(
        self,
        mocker: MockerFixture,
    ) -> None:
        # Arrange
        registry = _make_registry(mocker, providers=(_OLLAMA_CONFIG,))
        registry.load()

        # Act
        result = registry.get_config()

        # Assert
        assert result is not None
        assert len(result.providers) == 1
        assert result.providers[0].provider_id == "ollama_local"

    def test_get_config_returns_none_after_failed_load(
        self,
        mocker: MockerFixture,
    ) -> None:
        # Arrange
        mock_loader = mocker.Mock(spec=ProviderConfigLoaderApi)
        mock_loader.load.side_effect = ValueError("bad config")
        registry = ProviderRegistry(
            config_loader=mock_loader,
            providers_yaml_path=Path("providers.yaml"),
        )
        registry.load()

        # Act / Assert
        assert registry.get_config() is None

    def test_get_config_updates_after_reload(self, mocker: MockerFixture) -> None:
        # Arrange — first load has one provider, reload has two
        mocker.patch("ollama_llm_bench.backend.services.providers.openai_compatible_provider.openai.OpenAI")
        mocker.patch("ollama_llm_bench.backend.services.providers.openai_embedding_provider.openai.OpenAI")
        mock_loader = mocker.Mock(spec=ProviderConfigLoaderApi)
        config_a = ProvidersConfig(providers=(_OLLAMA_CONFIG,), embedding=_EMBEDDING_CONFIG)
        config_b = ProvidersConfig(providers=(_OLLAMA_CONFIG, _DISABLED_CONFIG), embedding=_EMBEDDING_CONFIG)
        mock_loader.load.side_effect = [config_a, config_b]
        registry = ProviderRegistry(
            config_loader=mock_loader,
            providers_yaml_path=Path("providers.yaml"),
        )
        registry.load()
        assert registry.get_config() is config_a

        # Act
        registry.reload()

        # Assert
        result = registry.get_config()
        assert result is config_b
        assert len(result.providers) == 2
