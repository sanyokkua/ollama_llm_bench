"""Service for loading and validating the providers.yaml configuration file."""

import logging
import os
import re
from pathlib import Path

import yaml

from ollama_llm_bench.backend.core.models import (
    EmbeddingConfig,
    ProviderConfig,
    ProvidersConfig,
    ProviderType,
)

_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")

logger = logging.getLogger(__name__)


class ProviderConfigLoader:
    """Loads and validates the providers.yaml configuration file.

    Resolves ${ENV_VAR} references in string fields. Missing environment
    variables produce a warning and are replaced with an empty string.
    """

    def load(self, path: Path) -> ProvidersConfig:
        """Load and validate a providers.yaml file.

        Args:
            path: Path to the providers.yaml file.

        Returns:
            Parsed and validated ProvidersConfig.

        Raises:
            ValueError: If the file contains no provider entries.
            OSError: If the file cannot be read.
        """
        with path.open(encoding="utf-8") as fh:
            raw: dict[str, object] = yaml.safe_load(fh) or {}

        raw_providers = raw.get("providers")
        if not raw_providers or not isinstance(raw_providers, list):
            raise ValueError("providers.yaml must contain at least one provider entry")

        providers = self._parse_providers(raw_providers)
        if not providers:
            raise ValueError("providers.yaml must contain at least one provider entry")

        embedding = self._parse_embedding(raw.get("embedding") or {})
        return ProvidersConfig(providers=tuple(providers), embedding=embedding)

    def get_enabled_providers(self, config: ProvidersConfig) -> list[ProviderConfig]:
        """Return only the enabled providers from a loaded config.

        Args:
            config: A previously loaded ProvidersConfig.

        Returns:
            List of ProviderConfig instances where enabled is True.
        """
        return [p for p in config.providers if p.enabled]

    def _parse_providers(self, entries: list[object]) -> list[ProviderConfig]:
        """Parse a list of raw provider dicts into ProviderConfig instances.

        Args:
            entries: Raw list from the YAML 'providers' key.

        Returns:
            List of successfully parsed ProviderConfig instances.
        """
        result: list[ProviderConfig] = []
        for entry in entries:
            if not isinstance(entry, dict):
                logger.warning("Skipping non-dict provider entry")
                continue
            parsed = self._parse_provider(entry)
            if parsed is not None:
                result.append(parsed)
        return result

    def _parse_provider(self, entry: dict[str, object]) -> ProviderConfig | None:
        """Parse a single provider dict.

        Args:
            entry: Raw provider dictionary from YAML.

        Returns:
            A ProviderConfig, or None if the entry is malformed.
        """
        provider_id = entry.get("id")
        if not provider_id or not isinstance(provider_id, str):
            logger.warning("Provider entry missing 'id', skipping")
            return None

        raw_type = entry.get("type")
        if not raw_type or not isinstance(raw_type, str):
            logger.warning("Provider '%s' missing 'type', skipping", provider_id)
            return None

        raw_api_key = entry.get("api_key")
        if raw_api_key is None:
            logger.warning("Provider '%s' missing 'api_key', skipping", provider_id)
            return None

        api_key_raw = str(raw_api_key)

        try:
            provider_type = ProviderType(raw_type)
        except ValueError:
            logger.warning("Provider '%s' has unknown type '%s', skipping", provider_id, raw_type)
            return None

        enabled_raw = entry.get("enabled", True)
        enabled = bool(enabled_raw)

        api_key = self._resolve_env(str(raw_api_key), provider_id=provider_id, field="api_key") if enabled else ""

        raw_base_url = entry.get("base_url")
        base_url: str | None = None
        if raw_base_url is not None:
            base_url = self._resolve_env(str(raw_base_url), provider_id=provider_id, field="base_url")

        raw_azure_deployment = entry.get("azure_deployment")
        azure_deployment: str | None = str(raw_azure_deployment) if raw_azure_deployment is not None else None

        raw_azure_api_version = entry.get("azure_api_version")
        azure_api_version: str | None = str(raw_azure_api_version) if raw_azure_api_version is not None else None

        raw_models = entry.get("default_models")
        default_models: tuple[str, ...] = ()
        if isinstance(raw_models, list):
            default_models = tuple(str(m) for m in raw_models)

        label_raw = entry.get("label", provider_id)
        label = str(label_raw) if label_raw is not None else provider_id

        return ProviderConfig(
            provider_id=provider_id,
            label=label,
            provider_type=provider_type,
            api_key=api_key,
            api_key_raw=api_key_raw,
            enabled=enabled,
            base_url=base_url,
            default_models=default_models,
            azure_deployment=azure_deployment,
            azure_api_version=azure_api_version,
        )

    def serialize_config(self, config: ProvidersConfig) -> dict[str, object]:
        """Serialize a ProvidersConfig to a YAML-dumpable dict.

        Uses api_key_raw (the unresolved placeholder or plain value) so that
        ${ENV_VAR} references survive a save round-trip intact.

        Args:
            config: The ProvidersConfig to serialize.

        Returns:
            A dict ready for yaml.safe_dump.
        """
        providers: list[dict[str, object]] = []
        for p in config.providers:
            entry: dict[str, object] = {
                "id": p.provider_id,
                "label": p.label,
                "type": p.provider_type.value,
                "api_key": p.api_key_raw,
                "enabled": p.enabled,
            }
            if p.base_url is not None:
                entry["base_url"] = p.base_url
            if p.default_models:
                entry["default_models"] = list(p.default_models)
            if p.azure_deployment is not None:
                entry["azure_deployment"] = p.azure_deployment
            if p.azure_api_version is not None:
                entry["azure_api_version"] = p.azure_api_version
            providers.append(entry)
        return {
            "providers": providers,
            "embedding": {
                "provider_id": config.embedding.provider_id,
                "model": config.embedding.model,
            },
        }

    def _parse_embedding(self, raw: object) -> EmbeddingConfig:
        """Parse the embedding config block.

        Args:
            raw: Raw value from the YAML 'embedding' key.

        Returns:
            EmbeddingConfig with defaults if the block is missing or malformed.
        """
        if not isinstance(raw, dict):
            logger.warning("'embedding' block missing or malformed; using defaults")
            return EmbeddingConfig(provider_id="ollama_local", model="bge-m3")

        provider_id = str(raw.get("provider_id") or "ollama_local")
        model = str(raw.get("model") or "bge-m3")
        return EmbeddingConfig(provider_id=provider_id, model=model)

    def _resolve_env(self, value: str, *, provider_id: str, field: str) -> str:
        """Replace ${VAR} references with environment variable values.

        Args:
            value: String that may contain ${ENV_VAR} placeholders.
            provider_id: Provider ID used in warning messages.
            field: Field name used in warning messages.

        Returns:
            String with all ${VAR} references substituted.
        """

        def replacer(m: re.Match[str]) -> str:
            var = m.group(1)
            resolved = os.environ.get(var, "")
            if not resolved:
                logger.warning(
                    "Environment variable '%s' is unset for provider '%s' field '%s'",
                    var,
                    provider_id,
                    field,
                )
            return resolved

        return _ENV_VAR_RE.sub(replacer, value)
