"""Composition root for all configured LLM and embedding provider clients."""

import logging
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import cast

from ollama_llm_bench.backend.core.interfaces import (
    EmbeddingProviderApi,
    LLMProviderApi,
    ModelCapabilityServiceApi,
    ProviderConfigLoaderApi,
    ProviderConfigRepositoryApi,
)
from ollama_llm_bench.backend.core.models import EmbeddingConfig, ProviderConfig, ProvidersConfig, ProviderType
from ollama_llm_bench.backend.services.embedding_service import EmbeddingService
from ollama_llm_bench.backend.services.llm_error_classifier import LlmErrorClassifier
from ollama_llm_bench.backend.services.model_name_parser import ModelNameParser
from ollama_llm_bench.backend.services.providers.anthropic_provider import AnthropicProvider
from ollama_llm_bench.backend.services.providers.gemini_provider import GeminiProvider
from ollama_llm_bench.backend.services.providers.openai_compatible_provider import OpenAICompatibleProvider
from ollama_llm_bench.backend.services.providers.openai_embedding_provider import OpenAIEmbeddingProvider

logger = logging.getLogger(__name__)


class ProviderNotFoundError(KeyError):
    """Raised when a provider_id is not found in the registry."""


def _build_openai_compatible(
    config: ProviderConfig,
    name_parser: ModelNameParser,
    capability_service: ModelCapabilityServiceApi | None = None,
    classifier: LlmErrorClassifier | None = None,
) -> LLMProviderApi:
    return cast(
        LLMProviderApi,
        OpenAICompatibleProvider(
            provider_id=config.provider_id,
            provider_type=config.provider_type.value,
            base_url=config.base_url or "",
            api_key=config.api_key,
            name_parser=name_parser,
            capability_service=capability_service,
            classifier=classifier,
        ),
    )


def _build_anthropic(config: ProviderConfig, name_parser: ModelNameParser) -> LLMProviderApi:
    return cast(
        LLMProviderApi,
        AnthropicProvider(
            provider_id=config.provider_id,
            api_key=config.api_key,
            default_models=config.default_models,
            base_url=config.base_url,
        ),
    )


def _build_gemini(config: ProviderConfig, name_parser: ModelNameParser) -> LLMProviderApi:
    return cast(
        LLMProviderApi,
        GeminiProvider(
            provider_id=config.provider_id,
            api_key=config.api_key,
            default_models=config.default_models,
            base_url=config.base_url,
        ),
    )


type _ProviderFactory = Callable[
    [ProviderConfig, ModelNameParser, ModelCapabilityServiceApi | None, LlmErrorClassifier | None],
    LLMProviderApi,
]


def _build_anthropic_factory(
    config: ProviderConfig,
    name_parser: ModelNameParser,
    capability_service: ModelCapabilityServiceApi | None = None,
    classifier: LlmErrorClassifier | None = None,
) -> LLMProviderApi:
    return _build_anthropic(config, name_parser)


def _build_gemini_factory(
    config: ProviderConfig,
    name_parser: ModelNameParser,
    capability_service: ModelCapabilityServiceApi | None = None,
    classifier: LlmErrorClassifier | None = None,
) -> LLMProviderApi:
    return _build_gemini(config, name_parser)


_PROVIDER_FACTORIES: dict[ProviderType, _ProviderFactory] = {
    ProviderType.OPENAI_COMPATIBLE: _build_openai_compatible,
    ProviderType.ANTHROPIC: _build_anthropic_factory,
    ProviderType.GEMINI: _build_gemini_factory,
}


class ProviderRegistry:
    """Composition root that constructs and exposes all configured LLM and embedding providers.

    Reads a providers.yaml file via the injected ProviderConfigLoaderApi, instantiates
    one provider client per enabled entry using a factory dispatch table, and makes
    providers available by ID or as filtered lists. Call load() before any accessor.
    """

    def __init__(
        self,
        *,
        config_loader: ProviderConfigLoaderApi,
        providers_yaml_path: Path,
        capability_service: ModelCapabilityServiceApi | None = None,
        classifier: LlmErrorClassifier | None = None,
        config_repository: ProviderConfigRepositoryApi | None = None,
    ) -> None:
        """Initialize the registry with a config loader and path to providers.yaml.

        Args:
            config_loader: Loader used to parse and validate the providers.yaml file.
            providers_yaml_path: Path to the providers.yaml configuration file.
            capability_service: Optional service for model capability discovery; forwarded
                to OpenAI-compatible providers so warm_up() can persist 400-error discoveries.
            classifier: Optional error classifier; forwarded to OpenAI-compatible providers.
            config_repository: Optional SQLite-backed repository; when provided and non-empty,
                providers are loaded from the database rather than from the YAML file.
        """
        self._config_loader = config_loader
        self._providers_yaml_path = providers_yaml_path
        self._capability_service = capability_service
        self._classifier = classifier
        self._config_repository = config_repository
        self._providers: dict[str, LLMProviderApi] = {}
        self._config: ProvidersConfig | None = None
        self._embedding_service: EmbeddingService | None = None
        self._is_loaded: bool = False
        self._name_parser = ModelNameParser()

    def _load_config_from_db(self) -> ProvidersConfig | None:
        """Attempt to load ProvidersConfig from the SQLite repository.

        Returns the config if the repository is set and contains rows,
        otherwise returns None so the caller falls back to YAML.

        Returns:
            ProvidersConfig from the database, or None if unavailable.
        """
        if self._config_repository is None:
            return None
        try:
            if self._config_repository.count() == 0:
                return None
            raw_providers = self._config_repository.load_all()
            resolved = self._config_loader.resolve_env_vars(raw_providers)
            embedding_cfg = self._config_repository.load_embedding_config()
            if embedding_cfg is None:
                embedding_cfg = EmbeddingConfig(provider_id="ollama_local", model="")
            return ProvidersConfig(providers=tuple(resolved), embedding=embedding_cfg)
        except Exception:
            logger.exception("provider_registry_db_load_failed")
            return None

    def _seed_db_from_yaml(self, config: ProvidersConfig) -> None:
        """Seed the SQLite repository from a freshly loaded YAML config.

        Called when the database is empty and YAML is the authoritative source.
        Archives providers.yaml after a successful seed so subsequent launches
        load from the database instead. Errors are logged and swallowed.

        Args:
            config: Freshly loaded ProvidersConfig from providers.yaml.
        """
        if self._config_repository is None:
            return
        try:
            for provider in config.providers:
                self._config_repository.save(provider)
            self._config_repository.save_embedding_config(config.embedding)
            logger.info("provider_registry_db_seeded_from_yaml")
        except Exception:
            logger.exception("provider_registry_db_seed_failed")
            return
        suffix = date.today().strftime("%Y%m%d")
        migrated_path = self._providers_yaml_path.with_suffix(f".yaml.migrated-{suffix}")
        try:
            self._providers_yaml_path.rename(migrated_path)
            logger.info("providers_yaml_archived", extra={"path": str(migrated_path)})
        except OSError:
            logger.warning("providers_yaml_rename_failed", extra={"path": str(self._providers_yaml_path)})

    def load(self) -> None:
        """Load provider configuration and construct all provider clients.

        Prefers the SQLite repository when it contains rows (dual-write migration
        path).  Falls back to providers.yaml and seeds the database on first use.
        Iterates over every ProviderConfig entry, dispatches to the appropriate
        factory function, and stores successfully built providers. If a provider
        fails to build, a warning is logged and that provider is skipped.
        After a successful load, the embedding service is also resolved.
        Errors during the full load are caught; the registry is left empty on failure.
        """
        try:
            config = self._load_config_from_db()
            if config is None:
                config = self._config_loader.load(self._providers_yaml_path)
                self._seed_db_from_yaml(config)
            providers: dict[str, LLMProviderApi] = {}
            for provider_config in config.providers:
                factory = _PROVIDER_FACTORIES.get(provider_config.provider_type)
                if factory is None:
                    logger.warning("Unknown provider type: %s", provider_config.provider_type)
                    continue
                try:
                    providers[provider_config.provider_id] = factory(
                        provider_config,
                        self._name_parser,
                        self._capability_service,
                        self._classifier,
                    )
                except Exception:
                    logger.exception(
                        "provider_build_failed",
                        extra={"provider_id": provider_config.provider_id},
                    )
            self._providers = providers
            self._config = config
            self._embedding_service = self._resolve_embedding(config)
        except Exception:
            logger.exception("provider_registry_load_failed")
            self._providers = {}
            self._config = None
            self._embedding_service = None
        finally:
            self._is_loaded = True

    def _resolve_embedding(self, config: ProvidersConfig) -> EmbeddingService | None:
        """Resolve and construct the embedding service from config.

        Args:
            config: Fully loaded providers configuration.

        Returns:
            Constructed EmbeddingService, or None if the embedding provider is
            missing or not of openai_compatible type.
        """
        embedding_provider_id = config.embedding.provider_id
        matching = next(
            (p for p in config.providers if p.provider_id == embedding_provider_id),
            None,
        )
        if matching is None:
            logger.warning("Embedding provider '%s' not found in providers", embedding_provider_id)
            return None
        if matching.provider_type != ProviderType.OPENAI_COMPATIBLE:
            logger.warning("Embedding provider '%s' must be openai_compatible type", embedding_provider_id)
            return None
        try:
            embedding_client = OpenAIEmbeddingProvider(
                base_url=matching.base_url or "",
                api_key=matching.api_key,
                model=config.embedding.model,
            )
            return EmbeddingService(provider=embedding_client)
        except Exception:
            logger.exception("embedding_provider_build_failed")
            return None

    def reload(self) -> None:
        """Reload providers.yaml and reconstruct all provider clients.

        Delegates to load(), replacing all previously held provider instances.
        """
        self.load()

    def get_config(self) -> ProvidersConfig | None:
        """Return the currently loaded ProvidersConfig.

        Returns:
            The loaded ProvidersConfig if load() has been called successfully,
            or None if load() has not been called or failed.
        """
        return self._config

    def _guard_loaded(self) -> None:
        if not self._is_loaded:
            raise RuntimeError("ProviderRegistry not loaded — call load() first")

    def get_provider(self, provider_id: str) -> LLMProviderApi:
        """Return a provider by its unique identifier.

        Args:
            provider_id: Identifier of the provider to retrieve.

        Returns:
            The LLMProviderApi instance registered under provider_id.

        Raises:
            RuntimeError: If load() has not been called yet.
            ProviderNotFoundError: If no provider with the given ID was built.
        """
        self._guard_loaded()
        try:
            return self._providers[provider_id]
        except KeyError:
            raise ProviderNotFoundError(f"Provider '{provider_id}' not found") from None

    def get_all_providers(self) -> list[LLMProviderApi]:
        """Return all successfully built providers regardless of enabled flag.

        Returns:
            List of all built LLMProviderApi instances; empty if load failed.

        Raises:
            RuntimeError: If load() has not been called yet.
        """
        self._guard_loaded()
        return list(self._providers.values())

    def get_enabled_providers(self) -> list[LLMProviderApi]:
        """Return only the providers whose config entry has enabled=True.

        Returns:
            List of enabled LLMProviderApi instances; empty if none are enabled
            or if the config was not loaded.

        Raises:
            RuntimeError: If load() has not been called yet.
        """
        self._guard_loaded()
        if self._config is None:
            return []
        enabled_ids = {p.provider_id for p in self._config.providers if p.enabled}
        return [provider for pid, provider in self._providers.items() if pid in enabled_ids]

    def get_embedding_provider(self) -> EmbeddingProviderApi:
        """Return the embedding provider for cosine similarity evaluation.

        Returns:
            EmbeddingProviderApi backed by the configured OpenAI-compatible
            embedding endpoint with LRU caching.

        Raises:
            RuntimeError: If load() has not been called yet, or if the embedding
                provider could not be resolved from config.
        """
        self._guard_loaded()
        if self._embedding_service is None:
            raise RuntimeError("Embedding provider not available")
        return self._embedding_service
