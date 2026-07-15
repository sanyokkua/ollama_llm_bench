"""DTOs owned by ``backend/import_export/`` (`06_IMPORT_FORMATS.md` §§2, 6, 8).

Every finding produced during validation carries one of three severities (§2); a
settings-import preview groups each surviving key against its current value (§8);
a provider-import preview groups each surviving entry the same way, but the apply
step always replaces the registry wholesale rather than merging it (§8, DD-55).
"""

from enum import StrEnum

import msgspec

from ollama_llm_bench.backend.domain import ProviderConfigDraft, SettingKey

__all__: list[str] = [
    "ImportFinding",
    "ImportFindingSeverity",
    "ImportPreviewGroup",
    "ProviderImportItem",
    "ProviderImportPreview",
    "ProviderImportResult",
    "SettingsImportItem",
    "SettingsImportPreview",
    "SettingsImportResult",
]


class ImportFindingSeverity(StrEnum):
    """The three-severity validation model shared across every import kind (§2)."""

    HARD_ERROR = "hard_error"
    SOFT_WARNING = "soft_warning"
    SOFT_INFO = "soft_info"


class ImportPreviewGroup(StrEnum):
    """The preview grouping a validated item is sorted into before apply (§8)."""

    ADDED = "added"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    SKIPPED = "skipped"


class ImportFinding(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One validation finding surfaced in the preview (§2, §6).

    ``item_key`` names the setting key or provider name the finding is about;
    ``None`` marks a file-level finding (e.g. a coerced ``schema_version``).
    """

    severity: ImportFindingSeverity
    item_key: str | None
    reason: str


class SettingsImportItem(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One surviving settings key's proposed change against its current value (§8)."""

    setting_key: SettingKey
    current_value: str | None
    imported_value: str | None
    group: ImportPreviewGroup


class SettingsImportPreview(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The full validated preview of one settings import (§6.2, §8).

    ``resolved_values`` is the exact merge payload ``apply_settings_import``
    passes to ``AppSettingsStore.upsert_settings`` on confirmation — a
    deliberate, narrow exception to "never a dict for structured data": it is a
    homogeneous key -> value map matching that store method's own signature.
    """

    items: tuple[SettingsImportItem, ...]
    findings: tuple[ImportFinding, ...]
    resolved_values: dict[SettingKey, str]


class ProviderImportItem(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One provider entry's preview row (§6.3, §8). ``draft`` is ``None`` when SKIPPED."""

    name: str
    group: ImportPreviewGroup
    draft: ProviderConfigDraft | None


class ProviderImportPreview(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The full validated preview of one provider-configuration import (§4, §6.3, §8)."""

    items: tuple[ProviderImportItem, ...]
    embedding_provider_name: str
    embedding_model_name: str
    findings: tuple[ImportFinding, ...]


class SettingsImportResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The outcome of one confirmed settings-import apply (§8)."""

    applied_count: int
    skipped_count: int


class ProviderImportResult(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The outcome of one confirmed provider-configuration import apply (§8)."""

    applied_count: int
    skipped_count: int
