"""Settings-import validation and preview building (`06_IMPORT_FORMATS.md` §3, §6.2, §8).

Each key in the file's ``settings`` mapping is checked against
``settings_key_catalog.SETTINGS_CATALOG``: an unknown key, a wrong-typed value, or
a constraint-violating value is skipped with a soft warning (§6.2/§7); a valid key
is grouped Added/Changed/Unchanged against ``AppSettingsStore.get_setting`` and
carried into ``resolved_values`` — the exact merge payload for
``AppSettingsStore.upsert_settings``.
"""

from typing import Any

from ollama_llm_bench.backend.domain import SettingKey
from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.import_export._internal.settings_key_catalog import (
    SETTINGS_CATALOG,
    SettingSpec,
    SettingValueType,
)
from ollama_llm_bench.backend.import_export._internal.yaml_io import (
    check_kind_matches,
    load_yaml_mapping,
    resolve_schema_version,
)
from ollama_llm_bench.backend.import_export.models import (
    ImportFinding,
    ImportFindingSeverity,
    ImportPreviewGroup,
    SettingsImportItem,
    SettingsImportPreview,
)
from ollama_llm_bench.backend.persistence.app_settings import AppSettingsStore

__all__: list[str] = ["build_settings_import_preview"]

_EXPECTED_KIND = "settings"


def _coerce_bool(_spec: SettingSpec, raw_value: Any) -> tuple[str | None, str | None]:
    if not isinstance(raw_value, bool):
        return None, "value is not a boolean"
    return ("true" if raw_value else "false"), None


def _coerce_enum(spec: SettingSpec, raw_value: Any) -> tuple[str | None, str | None]:
    enum_values = spec.enum_values or frozenset()
    if not isinstance(raw_value, str) or raw_value not in enum_values:
        return None, f"value must be one of {sorted(enum_values)}"
    return raw_value, None


def _coerce_string(_spec: SettingSpec, raw_value: Any) -> tuple[str | None, str | None]:
    if not isinstance(raw_value, str):
        return None, "value is not a string"
    return raw_value, None


def _coerce_int(spec: SettingSpec, raw_value: Any) -> tuple[str | None, str | None]:
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        return None, "value is not an integer"
    if spec.min_value is not None and raw_value < spec.min_value:
        return None, f"value must be >= {spec.min_value}"
    if spec.max_value is not None and raw_value > spec.max_value:
        return None, f"value must be <= {spec.max_value}"
    return str(raw_value), None


def _coerce_float(spec: SettingSpec, raw_value: Any) -> tuple[str | None, str | None]:
    if spec.allow_blank and isinstance(raw_value, str) and raw_value == "":
        return "", None
    if isinstance(raw_value, bool) or not isinstance(raw_value, int | float):
        return None, "value is not a number"
    numeric = float(raw_value)
    if spec.min_value is not None and numeric < spec.min_value:
        return None, f"value must be >= {spec.min_value}"
    if spec.max_value is not None and numeric > spec.max_value:
        return None, f"value must be <= {spec.max_value}"
    return str(numeric), None


_COERCERS: dict[SettingValueType, Any] = {
    SettingValueType.BOOL: _coerce_bool,
    SettingValueType.INT: _coerce_int,
    SettingValueType.FLOAT: _coerce_float,
    SettingValueType.ENUM: _coerce_enum,
    SettingValueType.STRING: _coerce_string,
}


def _coerce_value(spec: SettingSpec, raw_value: Any) -> tuple[str | None, str | None]:
    """Coerce one raw YAML value against its spec.

    Returns:
        A ``(storage_value, error_reason)`` pair — exactly one is ``None``.
    """
    coercer = _COERCERS[spec.value_type]
    result: tuple[str | None, str | None] = coercer(spec, raw_value)
    return result


def _build_item(
    key: SettingKey, imported_value: str, *, app_settings_store: AppSettingsStore
) -> SettingsImportItem:
    current_value = app_settings_store.get_setting(key)
    if current_value is None:
        group = ImportPreviewGroup.ADDED
    elif current_value != imported_value:
        group = ImportPreviewGroup.CHANGED
    else:
        group = ImportPreviewGroup.UNCHANGED
    return SettingsImportItem(
        setting_key=key,
        current_value=current_value,
        imported_value=imported_value,
        group=group,
    )


def build_settings_import_preview(
    file_path: str, *, app_settings_store: AppSettingsStore
) -> SettingsImportPreview:
    """Parse and fully validate a settings YAML file into a preview (§3, §6.2, §8).

    Args:
        file_path: The absolute path of the settings YAML file to import.
        app_settings_store: Read for each key's current value.

    Returns:
        The full validated preview.

    Raises:
        TaskFileError: The file could not be parsed at all.
        ConfigurationError: ``kind`` mismatches, ``schema_version`` is too new,
            or ``settings`` is missing or not a mapping.
    """
    raw = load_yaml_mapping(file_path)
    check_kind_matches(raw, expected_kind=_EXPECTED_KIND)
    findings: list[ImportFinding] = []
    schema_finding = resolve_schema_version(raw)
    if schema_finding is not None:
        findings.append(schema_finding)

    settings_raw = raw.get("settings")
    if not isinstance(settings_raw, dict):
        raise ConfigurationError(message=f"{file_path}: 'settings' is missing or not a mapping")

    items: list[SettingsImportItem] = []
    resolved_values: dict[SettingKey, str] = {}
    for key, raw_value in settings_raw.items():
        spec = SETTINGS_CATALOG.get(key)
        if spec is None:
            findings.append(
                ImportFinding(
                    severity=ImportFindingSeverity.SOFT_WARNING,
                    item_key=key,
                    reason="Unrecognised key — ignored",
                )
            )
            continue
        storage_value, error_reason = _coerce_value(spec, raw_value)
        if storage_value is None:
            findings.append(
                ImportFinding(
                    severity=ImportFindingSeverity.SOFT_WARNING,
                    item_key=key,
                    reason=f"Invalid value — key skipped ({error_reason})",
                )
            )
            continue
        resolved_values[key] = storage_value
        items.append(_build_item(key, storage_value, app_settings_store=app_settings_store))

    if not resolved_values:
        findings.append(
            ImportFinding(
                severity=ImportFindingSeverity.SOFT_WARNING,
                item_key=None,
                reason="No importable keys remain; import is a no-op",
            )
        )

    return SettingsImportPreview(
        items=tuple(items), findings=tuple(findings), resolved_values=resolved_values
    )
