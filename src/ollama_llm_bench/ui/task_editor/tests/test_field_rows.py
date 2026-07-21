"""Colocated unit/widget tests for the Field-editor pane's per-field-kind input
controls (STORY-069-AC-1).

Exercises ``_internal/field_rows.py``'s pure selection plus ``_internal/
field_editor.py``'s real Qt rendering together -- the acceptance criterion is
about what control renders for each field kind, which is a rendering concern
(``testing-standard-pyqt``: a widget is never replaced by a mock).
"""

from typing import Any, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)
import pytest
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.ui.task_editor._internal.field_editor import FieldEditorWidget
from ollama_llm_bench.ui.task_editor._internal.field_rows import select_field_rows
from ollama_llm_bench.ui.task_editor.models import FieldControlKind

_EXPECTED_CHIP_COUNT_AFTER_PASTE_SPLIT = 3

_BLANK_TASK: dict[str, Any] = {
    "task_id": "",
    "difficulty": "medium",
    "question": "",
    "golden_answer": "",
    "required_terms": {"exact": [], "semantic": [], "forbidden": []},
}


def _control_for(qtbot: QtBot, field_name: str) -> QWidget:
    rows = select_field_rows(task=_BLANK_TASK, task_validation=None)
    row = next(one_row for one_row in rows if one_row.field_name == field_name)
    widget = FieldEditorWidget()
    qtbot.addWidget(widget)
    widget.apply((row,), header_text="Editing: test")
    return cast(
        "QWidget", widget.findChild(QWidget, f"task_editor.field_editor.control.{field_name}")
    )


def _assert_control_matches_kind(control: QWidget, control_kind: FieldControlKind) -> None:
    """Branch on ``control_kind`` -- a helper, not the parametrized test body itself
    (`testing.md` bans an ``if``/``for`` inside the test body, not a called helper)."""
    if control_kind is FieldControlKind.IDENTIFIER:
        assert isinstance(control, QLineEdit)
        return
    if control_kind is FieldControlKind.LONG_TEXT:
        assert isinstance(control, QPlainTextEdit)
        return
    if control_kind is FieldControlKind.ENUM:
        assert isinstance(control, QComboBox)
        assert {control.itemText(i) for i in range(control.count())} == {"easy", "medium", "hard"}
        assert control.currentText() == "medium"
        return
    if control_kind is FieldControlKind.BOOLEAN:
        assert isinstance(control, QCheckBox)
        assert control.isChecked() is True
        return
    if control_kind is FieldControlKind.CHIP_LIST:
        assert control.findChild(QListWidget, "task_editor.field_editor.chip_list") is not None
        assert control.findChild(QLineEdit, "task_editor.field_editor.chip_input") is not None
        assert control.findChild(QPushButton, "task_editor.field_editor.chip_remove") is not None
        return
    pytest.fail(f"no assertion registered for control kind {control_kind!r}")


@pytest.mark.parametrize(
    ("field_name", "control_kind"),
    [
        ("task_id", FieldControlKind.IDENTIFIER),
        ("question", FieldControlKind.LONG_TEXT),
        ("difficulty", FieldControlKind.ENUM),
        ("cosine_enabled", FieldControlKind.BOOLEAN),
        ("required_terms.exact", FieldControlKind.CHIP_LIST),
    ],
    ids=["task_id", "question", "difficulty", "cosine_enabled", "required_terms"],
)
def test_control_kind_per_field(
    qtbot: QtBot, field_name: str, control_kind: FieldControlKind
) -> None:
    """Proves: STORY-069-AC-1

    For each field kind, the Field Row renders the specified input control:
    ``task_id`` a single-line identifier input, a long-text field an
    auto-growing multi-line input, ``difficulty`` a closed-enum dropdown,
    ``cosine_enabled`` a checkbox defaulting checked, and ``required_terms.*``
    a chip input exposing its list/add-input/remove-button parts.
    """
    # Arrange / Act
    with structlog.testing.capture_logs() as logs:
        control = _control_for(qtbot, field_name)

    # Assert
    _assert_control_matches_kind(control, control_kind)
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)


def test_chip_input_supports_add_remove_and_paste_split(qtbot: QtBot) -> None:
    """Proves: STORY-069-AC-1

    The ``required_terms.*`` chip input supports adding one term via Enter,
    adding several at once via a comma-separated paste-split, and removing a
    selected chip via the Remove button.
    """
    # Arrange
    control = _control_for(qtbot, "required_terms.exact")
    chip_list = cast(
        "QListWidget", control.findChild(QListWidget, "task_editor.field_editor.chip_list")
    )
    chip_input = cast(
        "QLineEdit", control.findChild(QLineEdit, "task_editor.field_editor.chip_input")
    )
    remove_button = cast(
        "QPushButton", control.findChild(QPushButton, "task_editor.field_editor.chip_remove")
    )

    # Act -- Enter commits a single chip
    qtbot.keyClicks(chip_input, "alpha")  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
    qtbot.keyClick(chip_input, Qt.Key.Key_Return)  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
    single_add_count = chip_list.count()

    # Act -- a comma-separated paste splits into two more chips
    chip_input.setText("beta,gamma,")
    paste_split_count = chip_list.count()

    # Act -- selecting the first chip and clicking Remove deletes it
    chip_list.setCurrentRow(0)
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        remove_button, Qt.MouseButton.LeftButton
    )
    remaining_texts = {chip_list.item(i).text() for i in range(chip_list.count())}

    # Assert
    assert single_add_count == 1
    assert paste_split_count == _EXPECTED_CHIP_COUNT_AFTER_PASTE_SPLIT
    assert "alpha" not in remaining_texts
    assert remaining_texts == {"beta", "gamma"}
