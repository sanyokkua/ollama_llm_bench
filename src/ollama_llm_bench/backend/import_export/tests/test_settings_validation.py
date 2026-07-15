"""Proves: STORY-038-AC-4 — settings-import offending-key handling (06_IMPORT_FORMATS.md §6.2, §7)."""

from pathlib import Path

import pytest

from ollama_llm_bench.backend.errors import ConfigurationError
from ollama_llm_bench.backend.import_export.models import ImportFindingSeverity, ImportPreviewGroup
from ollama_llm_bench.backend.import_export.tests.conftest import (
    FakeAppSettingsStore,
    make_service,
    write_yaml_mapping,
)


def test_settings_offending_key_skipped_valid_kept(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-4

    Given a settings import mixing an unknown key, a wrong-typed value, a
    constraint-violating value, and valid keys, when it is validated, then
    each offending key is soft-warning-skipped without aborting, and the
    valid keys remain applicable.
    """
    document = {
        "kind": "settings",
        "schema_version": 1,
        "settings": {
            "totally.unknown.key": "x",
            "benchmark.retry_count": "not-an-int",
            "eval.cosine_threshold": 5.0,
            "ui.theme": "dark",
            "benchmark.warmup_enabled": True,
        },
    }
    file_path = write_yaml_mapping(tmp_path, document)
    service = make_service()

    preview = service.build_settings_import_preview(file_path)

    offending_keys = {
        finding.item_key
        for finding in preview.findings
        if finding.severity is ImportFindingSeverity.SOFT_WARNING and finding.item_key is not None
    }
    assert offending_keys == {
        "totally.unknown.key",
        "benchmark.retry_count",
        "eval.cosine_threshold",
    }
    assert preview.resolved_values == {"ui.theme": "dark", "benchmark.warmup_enabled": "true"}


@pytest.mark.parametrize(
    ("setting_key", "invalid_value"),
    [
        ("benchmark.warmup_enabled", "not-a-bool"),
        ("benchmark.last_mode", "not_a_real_mode"),
        ("ui.window_geometry", 12345),
        ("benchmark.retry_count", -5),
        ("benchmark.retry_count", 999),
        ("benchmark.temperature", "not-a-number"),
        ("eval.cosine_threshold", -1.0),
    ],
    ids=[
        "bool_wrong_type",
        "enum_not_a_member",
        "string_wrong_type",
        "int_below_minimum",
        "int_above_maximum",
        "float_not_a_number",
        "float_below_minimum",
    ],
)
def test_settings_coercion_invalid_values_skipped(
    tmp_path: Path, setting_key: str, invalid_value: object
) -> None:
    """Proves: STORY-038-AC-4

    Each per-type coercion failure (wrong type, out-of-range, not-an-enum-
    member) is a soft-warning skip, never a hard error.
    """
    document = {"kind": "settings", "schema_version": 1, "settings": {setting_key: invalid_value}}
    file_path = write_yaml_mapping(tmp_path, document)
    service = make_service()

    preview = service.build_settings_import_preview(file_path)

    assert setting_key not in preview.resolved_values
    assert any(
        finding.severity is ImportFindingSeverity.SOFT_WARNING and finding.item_key == setting_key
        for finding in preview.findings
    )


def test_settings_import_allows_blank_value_for_allow_blank_float(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-4

    A blank string is a valid value for a setting whose spec explicitly
    allows blank (``benchmark.temperature``), not a coercion failure.
    """
    document = {"kind": "settings", "schema_version": 1, "settings": {"benchmark.temperature": ""}}
    file_path = write_yaml_mapping(tmp_path, document)
    service = make_service()

    preview = service.build_settings_import_preview(file_path)

    assert preview.resolved_values == {"benchmark.temperature": ""}


@pytest.mark.parametrize(
    ("current_value", "imported_value", "expected_group"),
    [
        (None, "dark", ImportPreviewGroup.ADDED),
        ("light", "dark", ImportPreviewGroup.CHANGED),
        ("dark", "dark", ImportPreviewGroup.UNCHANGED),
    ],
    ids=["no_current_value_is_added", "different_value_is_changed", "same_value_is_unchanged"],
)
def test_settings_import_item_group_reflects_current_value(
    tmp_path: Path,
    current_value: str | None,
    imported_value: str,
    expected_group: ImportPreviewGroup,
) -> None:
    """Proves: STORY-038-AC-4

    Each surviving key's preview item is grouped Added/Changed/Unchanged
    against its current stored value.
    """
    initial_values = {} if current_value is None else {"ui.theme": current_value}
    settings_store = FakeAppSettingsStore(initial_values=initial_values)
    document = {"kind": "settings", "schema_version": 1, "settings": {"ui.theme": imported_value}}
    file_path = write_yaml_mapping(tmp_path, document)
    service = make_service(app_settings_store=settings_store)

    preview = service.build_settings_import_preview(file_path)

    assert preview.items[0].group is expected_group


def test_settings_missing_or_not_mapping_is_hard_error(tmp_path: Path) -> None:
    """Proves: STORY-038-AC-4

    A ``settings`` top-level key that is missing or not a mapping aborts the
    whole import.
    """
    document = {"kind": "settings", "schema_version": 1, "settings": ["not", "a", "mapping"]}
    file_path = write_yaml_mapping(tmp_path, document)
    service = make_service()

    with pytest.raises(ConfigurationError):
        service.build_settings_import_preview(file_path)
