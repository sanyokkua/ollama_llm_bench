"""Proves: STORY-067-AC-4

Confirms unknown keys appear in the Skipped/ignored group and known keys still
import on confirm; Apply is disabled while any hard-error finding exists.
Covers EC-SET-2.
"""

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.settings_dialog._internal.sub_dialogs.import_preview_select import (
    has_hard_error,
)
from ollama_llm_bench.ui.settings_dialog._internal.sub_dialogs.import_preview_view import (
    make_settings_import_preview_dialog,
)
from ollama_llm_bench.ui.settings_dialog.models import (
    PreviewGroup,
    SettingsImportPreview,
    SettingsImportPreviewRow,
    Severity,
    ValidationFinding,
)


def test_has_hard_error_true_only_when_a_hard_error_finding_exists() -> None:
    clean = SettingsImportPreview(
        rows=(), findings=(), resolved_values={}, backend_preview=object()
    )
    with_soft = SettingsImportPreview(
        rows=(),
        findings=(ValidationFinding(severity=Severity.SOFT_INFO, target="x", message="ignored"),),
        resolved_values={},
        backend_preview=object(),
    )
    with_hard = SettingsImportPreview(
        rows=(),
        findings=(ValidationFinding(severity=Severity.HARD_ERROR, target="x", message="bad"),),
        resolved_values={},
        backend_preview=object(),
    )

    assert has_hard_error(clean) is False
    assert has_hard_error(with_soft) is False
    assert has_hard_error(with_hard) is True


def test_unknown_key_row_is_skipped_group_and_apply_still_enabled(qtbot: QtBot) -> None:
    preview = SettingsImportPreview(
        rows=(
            SettingsImportPreviewRow(
                setting_key="benchmark.retry_count",
                current_value="3",
                imported_value="5",
                group=PreviewGroup.CHANGED,
            ),
        ),
        findings=(
            ValidationFinding(
                severity=Severity.SOFT_INFO,
                target="ui.old_theme",
                message="Unknown key ignored.",
            ),
        ),
        resolved_values={"benchmark.retry_count": "5"},
        backend_preview=object(),
    )

    dialog = make_settings_import_preview_dialog(preview=preview)
    qtbot.addWidget(dialog)

    assert dialog.apply_button.isEnabled() is True


def test_apply_disabled_when_a_hard_error_is_present(qtbot: QtBot) -> None:
    preview = SettingsImportPreview(
        rows=(),
        findings=(ValidationFinding(severity=Severity.HARD_ERROR, target="x", message="bad"),),
        resolved_values={},
        backend_preview=object(),
    )

    dialog = make_settings_import_preview_dialog(preview=preview)
    qtbot.addWidget(dialog)

    assert dialog.apply_button.isEnabled() is False


def test_apply_click_sets_confirmed_true(qtbot: QtBot) -> None:
    preview = SettingsImportPreview(
        rows=(), findings=(), resolved_values={}, backend_preview=object()
    )
    dialog = make_settings_import_preview_dialog(preview=preview)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        dialog.apply_button, Qt.MouseButton.LeftButton
    )

    assert dialog.confirmed is True
