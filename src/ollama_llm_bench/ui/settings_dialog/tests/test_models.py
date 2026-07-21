"""Proves: STORY-067-AC-2

Confirms the new validation/import DTOs construct as frozen, kw_only structs.
"""

import msgspec
import pytest

from ollama_llm_bench.ui.settings_dialog.models import (
    DialogChromeViewModel,
    PreviewGroup,
    ProviderImportPreview,
    ProviderImportPreviewRow,
    ProviderImportResult,
    SettingsImportPreview,
    SettingsImportPreviewRow,
    SettingsImportResult,
    Severity,
    ValidationFinding,
)


def test_validation_finding_is_frozen_kw_only() -> None:
    finding = ValidationFinding(
        severity=Severity.HARD_ERROR, target="providers[0].name", message="Duplicate name."
    )
    with pytest.raises((msgspec.ValidationError, AttributeError, TypeError)):
        finding.message = "changed"  # type: ignore[misc]  # proves frozen struct rejects mutation


def test_dialog_chrome_view_model_carries_save_enabled_and_general_tab_label() -> None:
    chrome = DialogChromeViewModel(
        providers_tab_label="Providers",
        general_tab_label="General*",
        save_state_text="Unsaved changes",
        dirty=True,
        save_enabled=False,
    )
    assert chrome.general_tab_label == "General*"
    assert chrome.save_enabled is False


def test_settings_import_preview_groups_rows_by_preview_group() -> None:
    row = SettingsImportPreviewRow(
        setting_key="benchmark.retry_count",
        current_value="3",
        imported_value="5",
        group=PreviewGroup.CHANGED,
    )
    preview = SettingsImportPreview(
        rows=(row,),
        findings=(
            ValidationFinding(
                severity=Severity.SOFT_INFO, target="ui.old_theme", message="Unknown key ignored."
            ),
        ),
        resolved_values={"benchmark.retry_count": "5"},
    )
    assert preview.rows[0].group is PreviewGroup.CHANGED
    assert preview.resolved_values["benchmark.retry_count"] == "5"


def test_provider_import_preview_and_results_construct() -> None:
    row = ProviderImportPreviewRow(name="OpenAI", group=PreviewGroup.ADDED)
    preview = ProviderImportPreview(
        rows=(row,),
        embedding_provider_name="OpenAI",
        embedding_model_name="text-embedding-3-small",
        findings=(),
    )
    result = ProviderImportResult(applied_count=1, skipped_count=0)
    assert preview.rows[0].name == "OpenAI"
    assert result.applied_count == 1


def test_settings_import_result_constructs() -> None:
    expected_applied_count = 12
    expected_skipped_count = 2
    result = SettingsImportResult(
        applied_count=expected_applied_count, skipped_count=expected_skipped_count
    )
    assert result.applied_count == expected_applied_count
    assert result.skipped_count == expected_skipped_count
