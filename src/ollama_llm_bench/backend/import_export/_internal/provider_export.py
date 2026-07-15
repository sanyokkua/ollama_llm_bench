"""``export_providers()`` YAML assembly (`06_IMPORT_FORMATS.md` §4, §9).

The exported ``providers`` sequence never carries ``provider_id`` (DD-33, §9) — a
re-import always generates a fresh UUID4 on insert. The embedding selection is
read from the two ``app_settings`` keys (D-R-13) and exported by provider name.
"""

from typing import Any

from ollama_llm_bench.backend.domain import ProviderConfig
from ollama_llm_bench.backend.import_export._internal.yaml_io import (
    SUPPORTED_SCHEMA_VERSION,
    dump_yaml_mapping,
)
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore
from ollama_llm_bench.backend.persistence.providers import ProvidersStore

__all__: list[str] = ["export_providers"]

_EMBEDDING_PROVIDER_NAME_KEY = "embedding.selected_provider_name"
_EMBEDDING_MODEL_NAME_KEY = "embedding.selected_model_name"


def _provider_entry(provider: ProviderConfig) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": provider.name,
        "type": provider.provider_type.value,
        "base_url": provider.base_url,
        "api_key": provider.api_key_raw or "",
        "enabled": provider.enabled,
        "default_models": list(provider.default_models),
    }
    if provider.azure_endpoint_raw is not None:
        entry["azure_endpoint"] = provider.azure_endpoint_raw
    if provider.azure_deployment_raw is not None:
        entry["azure_deployment"] = provider.azure_deployment_raw
    if provider.azure_api_version_raw is not None:
        entry["azure_api_version"] = provider.azure_api_version_raw
    return entry


def export_providers(
    *, providers_store: ProvidersStore, app_settings_store: AppSettingsStore
) -> bytes:
    """Serialize the provider catalog and embedding selection to YAML (§4, §9).

    Args:
        providers_store: Read via ``list_providers`` for the full catalog.
        app_settings_store: Read for the ``embedding.selected_*`` keys.

    Returns:
        The UTF-8-encoded YAML document.

    Raises:
        PersistenceError: The underlying read failed.
    """
    providers = providers_store.list_providers()
    document: dict[str, Any] = {
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "kind": "provider_config",
        "embedding": {
            "provider_name": app_settings_store.get_setting(_EMBEDDING_PROVIDER_NAME_KEY) or "",
            "model_name": app_settings_store.get_setting(_EMBEDDING_MODEL_NAME_KEY) or "",
        },
        "providers": [_provider_entry(provider) for provider in providers],
    }
    return dump_yaml_mapping(document)
