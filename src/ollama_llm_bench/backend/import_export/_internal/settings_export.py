"""``export_settings()`` YAML assembly (`06_IMPORT_FORMATS.md` §3, §9).

Only the keys the settings key catalogue recognises are exported — the round-trip
guarantee (§9) is scoped to user-importable keys, and every user-saved key is, by
construction of the settings registry, one this catalogue recognises. Each value
is rendered as its **native** YAML type (bool/int/float/string), matching the
canonical form shown in §3's worked example and the ``_coerce_*`` helpers'
expectation that a hand-authored or re-exported value is YAML-typed, not a
quoted numeral — a plain string round-trips as a plain string either way.
"""

from typing import Any

from ollama_llm_bench.backend.domain import SettingKey
from ollama_llm_bench.backend.import_export._internal.settings_key_catalog import (
    SETTINGS_CATALOG,
    SettingSpec,
    SettingValueType,
)
from ollama_llm_bench.backend.import_export._internal.yaml_io import (
    SUPPORTED_SCHEMA_VERSION,
    dump_yaml_mapping,
)
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore

__all__: list[str] = ["export_settings"]


def _to_native(spec: SettingSpec, storage_value: str) -> Any:
    """Render one stored TEXT value back to its native YAML type for export."""
    if spec.value_type is SettingValueType.BOOL:
        return storage_value == "true"
    if spec.value_type is SettingValueType.INT:
        return int(storage_value)
    if spec.value_type is SettingValueType.FLOAT:
        if spec.allow_blank and storage_value == "":
            return ""
        return float(storage_value)
    return storage_value


def _exportable_settings(app_settings_store: AppSettingsStore) -> dict[SettingKey, Any]:
    settings_values = app_settings_store.list_settings()
    exportable: dict[SettingKey, Any] = {}
    for key, storage_value in settings_values.items():
        spec = SETTINGS_CATALOG.get(key)
        if spec is None:
            continue
        exportable[key] = _to_native(spec, storage_value)
    return exportable


def export_settings(*, app_settings_store: AppSettingsStore) -> bytes:
    """Serialize every user-saved setting to the canonical settings YAML (§3, §9).

    Args:
        app_settings_store: Read via ``list_settings`` for the full row set.

    Returns:
        The UTF-8-encoded YAML document.

    Raises:
        PersistenceError: The underlying read failed.
    """
    document: dict[str, Any] = {
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "kind": "settings",
        "settings": _exportable_settings(app_settings_store),
    }
    return dump_yaml_mapping(document)
