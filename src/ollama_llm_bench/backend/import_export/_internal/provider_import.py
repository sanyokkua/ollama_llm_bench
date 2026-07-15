"""Provider-configuration import validation and preview building.

Source of truth: `06_IMPORT_FORMATS.md` §4 (schema), §5 (D-R-18 env-var-name-only
``api_key`` rule), §6.3 (validation checks), §8 (preview/replace semantics, DD-55).

Every surviving entry's name is checked against ``ProvidersStore.get_by_name``: a
collision is a soft warning excluding that entry from the applied set (EC-IMP-13).
The apply step therefore replaces the registry wholesale with exactly the entries
that survived every hard-error and soft-warning exclusion (§8, DD-55).
"""

import os
import re
from typing import Any, cast
from urllib.parse import urlparse

from ollama_llm_bench.backend.domain import ProviderConfigDraft, ProviderType
from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.import_export._internal.yaml_io import (
    check_kind_matches,
    load_yaml_mapping,
    resolve_schema_version,
)
from ollama_llm_bench.backend.import_export.models import (
    ImportFinding,
    ImportFindingSeverity,
    ImportPreviewGroup,
    ProviderImportItem,
    ProviderImportPreview,
)
from ollama_llm_bench.backend.persistence.providers import ProvidersStore

__all__: list[str] = ["build_provider_import_preview"]

_EXPECTED_KIND = "provider_config"
_ALLOWED_PROVIDER_TYPES: frozenset[str] = frozenset(
    {ProviderType.OPENAI_COMPATIBLE.value, ProviderType.ANTHROPIC.value, ProviderType.GEMINI.value}
)
_ENV_VAR_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_valid_api_key_value(value: Any) -> bool:
    """Return whether ``value`` is empty or a syntactically valid env-var name (§5)."""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return value == "" or _ENV_VAR_NAME_PATTERN.match(value) is not None


def _is_valid_base_url(value: str) -> bool:
    """Return whether ``value`` is a syntactically valid URL (§6.3, DD-55).

    Mirrors the provider-edit dialog's own base-URL syntax rule
    (`06_Settings_Dialog/sub_dialogs/provider_edit.md` §4): an ``http``/``https``
    scheme plus a non-empty network location.
    """
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _env_var_findings(entry: dict[str, Any], *, name: str) -> list[ImportFinding]:
    """Flag an env-var-name ``api_key`` naming a currently-unset variable (§5, EC-IMP-10)."""
    api_key_raw = entry.get("api_key")
    if not isinstance(api_key_raw, str) or not api_key_raw:
        return []
    if os.environ.get(api_key_raw) is not None:
        return []
    return [
        _finding(
            ImportFindingSeverity.SOFT_WARNING,
            name,
            f"Environment variable `{api_key_raw}` is not currently set",
        )
    ]


def _optional_str(entry: dict[str, Any], field_name: str) -> str | None:
    value = entry.get(field_name)
    return value if isinstance(value, str) and value else None


def _default_models(entry: dict[str, Any]) -> tuple[str, ...]:
    raw_models = entry.get("default_models")
    if not isinstance(raw_models, list):
        return ()
    return tuple(model for model in raw_models if isinstance(model, str))


def _check_duplicate_names(providers_raw: list[Any], file_path: str) -> None:
    """Abort the whole import when two entries share a ``name`` (§6.3, EC-IMP-7)."""
    seen: set[str] = set()
    for entry in providers_raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        if name in seen:
            raise ConfigurationError(
                message=f"{file_path}: provider name {name!r} is used by more than one entry"
            )
        seen.add(name)


def _structural_error_reason(
    entry: dict[str, Any], *, name: Any, provider_type_raw: Any
) -> str | None:
    """Return the hard-error reason for a structurally invalid entry, or ``None``."""
    if not isinstance(name, str) or not name or not provider_type_raw:
        return "Provider entry missing 'name' or 'type'"
    if provider_type_raw not in _ALLOWED_PROVIDER_TYPES:
        return f"type {provider_type_raw!r} is not one of {sorted(_ALLOWED_PROVIDER_TYPES)}"
    provider_type = ProviderType(provider_type_raw)
    base_url = _optional_str(entry, "base_url")
    if provider_type is ProviderType.OPENAI_COMPATIBLE and not base_url:
        return "openai_compatible entry is missing base_url"
    if base_url is not None and not _is_valid_base_url(base_url):
        return f"base_url {base_url!r} is not a syntactically valid URL"
    if not _is_valid_api_key_value(entry.get("api_key")):
        return "api_key is a literal secret value; an environment-variable name is required"
    return None


def _validate_entry(
    entry: Any, *, providers_store: ProvidersStore
) -> tuple[ProviderImportItem | None, ProviderConfigDraft | None, list[ImportFinding]]:
    """Validate one raw provider entry.

    Returns:
        ``(item, draft, findings)`` — ``item``/``draft`` are ``None`` when the
        entry has no usable ``name`` to key a preview row on; ``draft`` is
        additionally ``None`` (with ``item`` present) when the entry is SKIPPED.
    """
    if not isinstance(entry, dict):
        return (
            None,
            None,
            [_finding(ImportFindingSeverity.HARD_ERROR, None, "entry is not a mapping")],
        )

    raw_name = entry.get("name")
    provider_type_raw = entry.get("type")
    reason = _structural_error_reason(entry, name=raw_name, provider_type_raw=provider_type_raw)
    if reason is not None:
        item = _skipped_item(raw_name) if isinstance(raw_name, str) and raw_name else None
        return (
            item,
            None,
            [
                _finding(
                    ImportFindingSeverity.HARD_ERROR,
                    item.name if item is not None else None,
                    reason,
                )
            ],
        )
    name = cast("str", raw_name)

    findings: list[ImportFinding] = []
    if "id" in entry:
        findings.append(
            _finding(
                ImportFindingSeverity.SOFT_INFO,
                name,
                "Field retired — provider_id is now auto-generated",
            )
        )
    findings.extend(_env_var_findings(entry, name=name))

    if providers_store.get_by_name(name) is not None:
        findings.append(
            _finding(
                ImportFindingSeverity.SOFT_WARNING, name, "Duplicate name — already in catalog"
            )
        )
        return _skipped_item(name), None, findings

    draft = _build_draft(entry, name=name, provider_type_raw=provider_type_raw)
    item = ProviderImportItem(name=name, group=ImportPreviewGroup.ADDED, draft=draft)
    return item, draft, findings


def _build_draft(
    entry: dict[str, Any], *, name: str, provider_type_raw: Any
) -> ProviderConfigDraft:
    api_key_raw = entry.get("api_key")
    enabled_raw = entry.get("enabled")
    return ProviderConfigDraft(
        name=name,
        provider_type=ProviderType(provider_type_raw),
        enabled=enabled_raw if isinstance(enabled_raw, bool) else False,
        base_url=_optional_str(entry, "base_url"),
        api_key_raw=api_key_raw if isinstance(api_key_raw, str) and api_key_raw else None,
        azure_endpoint_raw=_optional_str(entry, "azure_endpoint"),
        azure_deployment_raw=_optional_str(entry, "azure_deployment"),
        azure_api_version_raw=_optional_str(entry, "azure_api_version"),
        default_models=_default_models(entry),
    )


def _skipped_item(name: str) -> ProviderImportItem:
    return ProviderImportItem(name=name, group=ImportPreviewGroup.SKIPPED, draft=None)


def _finding(severity: ImportFindingSeverity, item_key: str | None, reason: str) -> ImportFinding:
    return ImportFinding(severity=severity, item_key=item_key, reason=reason)


def _resolve_embedding_selection(
    embedding_raw: dict[str, Any], *, surviving_names: frozenset[str], file_path: str
) -> tuple[str, str]:
    provider_name = embedding_raw.get("provider_name")
    model_name = embedding_raw.get("model_name")
    if not isinstance(provider_name, str) or provider_name not in surviving_names:
        raise ConfigurationError(
            message=(
                f"{file_path}: embedding.provider_name {provider_name!r} matches no "
                "surviving provider entry"
            )
        )
    return provider_name, model_name if isinstance(model_name, str) else ""


def build_provider_import_preview(
    file_path: str, *, providers_store: ProvidersStore
) -> ProviderImportPreview:
    """Parse and fully validate a provider-configuration YAML file (§4, §6.3, §8).

    Args:
        file_path: The absolute path of the provider-config YAML file to import.
        providers_store: Pre-checked via ``get_by_name`` for each surviving entry.

    Returns:
        The full validated preview.

    Raises:
        TaskFileError: The file could not be parsed at all.
        ConfigurationError: ``kind`` mismatches, ``schema_version`` is too new,
            ``providers``/``embedding`` are missing or wrong-shaped, every entry
            is dropped, two entries share a ``name``, or ``embedding.provider_name``
            matches no surviving entry.
    """
    raw = load_yaml_mapping(file_path)
    check_kind_matches(raw, expected_kind=_EXPECTED_KIND)
    findings: list[ImportFinding] = []
    schema_finding = resolve_schema_version(raw)
    if schema_finding is not None:
        findings.append(schema_finding)

    providers_raw = raw.get("providers")
    if not isinstance(providers_raw, list) or not providers_raw:
        raise ConfigurationError(
            message=f"{file_path}: 'providers' is missing, empty, or not a list"
        )
    embedding_raw = raw.get("embedding")
    if not isinstance(embedding_raw, dict):
        raise ConfigurationError(message=f"{file_path}: 'embedding' is missing or not a mapping")

    _check_duplicate_names(providers_raw, file_path)

    items: list[ProviderImportItem] = []
    surviving_names: set[str] = set()
    structurally_valid_count = 0
    for entry in providers_raw:
        item, draft, entry_findings = _validate_entry(entry, providers_store=providers_store)
        findings.extend(entry_findings)
        if item is not None:
            items.append(item)
        is_hard_error = any(
            finding.severity is ImportFindingSeverity.HARD_ERROR for finding in entry_findings
        )
        if not is_hard_error:
            structurally_valid_count += 1
        if draft is not None:
            surviving_names.add(draft.name)

    if structurally_valid_count == 0:
        raise ConfigurationError(message=f"{file_path}: every provider entry was dropped")

    embedding_provider_name, embedding_model_name = _resolve_embedding_selection(
        embedding_raw, surviving_names=frozenset(surviving_names), file_path=file_path
    )

    return ProviderImportPreview(
        items=tuple(items),
        embedding_provider_name=embedding_provider_name,
        embedding_model_name=embedding_model_name,
        findings=tuple(findings),
    )
