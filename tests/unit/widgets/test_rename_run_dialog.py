"""Unit tests for RenameRunDialog — validation logic and OK button state."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from ollama_llm_bench.ui.widgets.panels.rename_run_dialog import RenameRunDialog


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


def _make_dialog(
    qapp: QApplication,
    current_name: str = "My Run",
    existing_names: frozenset[str] | None = None,
) -> RenameRunDialog:
    return RenameRunDialog(
        current_name=current_name,
        existing_names=existing_names or frozenset(),
    )


def _ok_enabled(dlg: RenameRunDialog) -> bool:
    btn = dlg._btn_box.button(QDialogButtonBox.StandardButton.Ok)
    assert btn is not None
    return btn.isEnabled()


def test_ok_disabled_when_empty(qapp: QApplication) -> None:
    dlg = _make_dialog(qapp)
    dlg._line_edit.setText("")
    assert not _ok_enabled(dlg)


def test_ok_disabled_when_too_long(qapp: QApplication) -> None:
    dlg = _make_dialog(qapp)
    dlg._line_edit.setText("x" * 81)
    assert not _ok_enabled(dlg)


def test_ok_disabled_at_exactly_max_len(qapp: QApplication) -> None:
    dlg = _make_dialog(qapp)
    dlg._line_edit.setText("x" * 80)
    assert _ok_enabled(dlg)


def test_ok_disabled_when_control_chars(qapp: QApplication) -> None:
    dlg = _make_dialog(qapp)
    dlg._line_edit.setText("valid\x00name")
    assert not _ok_enabled(dlg)


def test_ok_disabled_when_control_tab(qapp: QApplication) -> None:
    dlg = _make_dialog(qapp)
    dlg._line_edit.setText("valid\tname")
    assert not _ok_enabled(dlg)


def test_ok_disabled_when_duplicate_exact(qapp: QApplication) -> None:
    dlg = _make_dialog(qapp, existing_names=frozenset({"my run"}))
    dlg._line_edit.setText("my run")
    assert not _ok_enabled(dlg)


def test_ok_disabled_when_duplicate_case_insensitive(qapp: QApplication) -> None:
    dlg = _make_dialog(qapp, existing_names=frozenset({"my run"}))
    dlg._line_edit.setText("MY RUN")
    assert not _ok_enabled(dlg)


def test_ok_enabled_for_valid_name(qapp: QApplication) -> None:
    dlg = _make_dialog(qapp, existing_names=frozenset({"other run"}))
    dlg._line_edit.setText("New Run Name")
    assert _ok_enabled(dlg)


def test_new_name_returns_stripped_text(qapp: QApplication) -> None:
    dlg = _make_dialog(qapp)
    dlg._line_edit.setText("  trimmed  ")
    assert dlg.new_name == "trimmed"


def test_error_label_hidden_when_valid(qapp: QApplication) -> None:
    dlg = _make_dialog(qapp)
    dlg._line_edit.setText("Valid Name")
    assert dlg._error_label.isHidden()


def test_error_label_visible_when_invalid(qapp: QApplication) -> None:
    dlg = _make_dialog(qapp)
    dlg._line_edit.setText("")
    assert not dlg._error_label.isHidden()


def test_pre_filled_with_current_name(qapp: QApplication) -> None:
    dlg = _make_dialog(qapp, current_name="Existing Name")
    assert dlg._line_edit.text() == "Existing Name"
