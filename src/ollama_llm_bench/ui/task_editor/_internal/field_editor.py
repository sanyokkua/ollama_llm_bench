"""The Field-editor pane -- the scrollable Form, Field Rows, collapsible groups, help
popovers, and per-field validation strips (STORY-069-AC-1; ``description.md`` §3.5).

The help "popover" is a plain ``QMessageBox.information`` triggered by the round help
button (which also carries a hover tooltip) -- no bespoke Popover overlay widget is
built this story: ``TaskEditorCollaborators`` intentionally carries no
``ThemeManager`` (STORY-068 design decision), and a custom popover surface with no
existing precedent anywhere in the codebase is a disproportionate addition for one
help affordance when the built-in modal already satisfies "hover or click reveals the
field's help text" (§3.5). The reserved ``popover_blur``/``popover_offset_y`` theme
tokens remain for a future dedicated Popover widget.

This pane always fully rebuilds its row widgets on ``apply()`` (matching
``files_pane.py``/``tasks_pane.py``'s own clear-and-rebuild precedent) -- an edit that
is mid-keystroke never reaches ``apply()`` because a re-render is only ever
triggered after the validation debounce fires (i.e. the user has already paused) or
on focus loss, so no rebuild interrupts an in-flight keystroke; the pane's identity
still resets on every rebuild (a known limitation, noted in the owning story).
"""

from functools import partial

from PySide6.QtCore import Signal
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.domain import Difficulty
from ollama_llm_bench.ui.task_editor._internal.field_rows import FIELD_GROUPS
from ollama_llm_bench.ui.task_editor._internal.theme_lookup import monospace_font
from ollama_llm_bench.ui.task_editor.models import (
    FieldControlKind,
    FieldRowViewModel,
    ValidationState,
)

__all__: list[str] = ["FieldEditorWidget"]

_STATE_LABEL: dict[ValidationState, str] = {
    ValidationState.CLEAN: "Valid",
    ValidationState.INFO: "Info",
    ValidationState.WARNING: "Warning",
    ValidationState.ERROR: "Error",
}
_MONOSPACE_FIELD = "golden_answer"
_TRUE_STR = "true"


class _FocusOutLineEdit(QLineEdit):
    """A ``QLineEdit`` that additionally announces focus loss (blur commits, §2 of
    ``state_machine.md``)."""

    focus_lost = Signal()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        self.focus_lost.emit()


class _FocusOutPlainTextEdit(QPlainTextEdit):
    """A ``QPlainTextEdit`` that additionally announces focus loss."""

    focus_lost = Signal()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        self.focus_lost.emit()


class _ChipInputWidget(QWidget):
    """Add/remove/paste-split chip input for a ``required_terms.*`` list (§3.5.1)."""

    values_changed = Signal(object)  # tuple[str, ...]

    def __init__(self) -> None:
        super().__init__()
        self._values: tuple[str, ...] = ()
        layout = QVBoxLayout(self)
        self._list = QListWidget()
        self._list.setObjectName("task_editor.field_editor.chip_list")
        layout.addWidget(self._list)

        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setObjectName("task_editor.field_editor.chip_input")
        self._input.setAccessibleName("Add chip value")
        self._input.setPlaceholderText("Type a term, comma or Enter to add")
        self._input.textChanged.connect(self._on_input_text_changed)
        self._input.returnPressed.connect(self._commit_input)
        row.addWidget(self._input)

        self._remove_button = QPushButton("Remove")
        self._remove_button.setObjectName("task_editor.field_editor.chip_remove")
        self._remove_button.setAccessibleName("Remove selected chip values")
        self._remove_button.clicked.connect(self._on_remove_clicked)
        row.addWidget(self._remove_button)
        layout.addLayout(row)

    def set_values(self, values: tuple[str, ...]) -> None:
        """Push the field's current chip list without emitting ``values_changed``."""
        self._values = values
        self._list.clear()
        self._list.addItems(values)

    def _on_input_text_changed(self, text: str) -> None:
        if "," not in text:
            return
        *chip_texts, remainder = text.split(",")
        added = tuple(chip.strip() for chip in chip_texts if chip.strip())
        if added:
            self._add_chips(added)
        self._input.blockSignals(True)  # noqa: FBT003  # Qt's own blockSignals(bool) API
        self._input.setText(remainder)
        self._input.blockSignals(False)  # noqa: FBT003  # Qt's own blockSignals(bool) API

    def _commit_input(self) -> None:
        text = self._input.text().strip()
        if text:
            self._add_chips((text,))
        self._input.clear()

    def _add_chips(self, chips: tuple[str, ...]) -> None:
        new_values = list(self._values)
        for chip in chips:
            if chip not in new_values:
                new_values.append(chip)
        self.set_values(tuple(new_values))
        self.values_changed.emit(self._values)

    def _on_remove_clicked(self) -> None:
        selected = self._list.selectedItems()
        if not selected:
            return
        removed_texts = {item.text() for item in selected}
        self.set_values(tuple(value for value in self._values if value not in removed_texts))
        self.values_changed.emit(self._values)


def _clear_layout(layout: QLayout) -> None:
    """Remove and destroy every widget item ``layout`` directly holds.

    Only ``addWidget``/``addStretch`` items are ever placed directly on
    ``FieldEditorWidget._form_layout`` (each row/group is its own self-contained
    ``QWidget`` with its own internal layout) -- no nested sub-layout is ever added
    to this layout, so a widget-only sweep is sufficient.
    """
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


class FieldEditorWidget(QWidget):
    """Passive Field-editor pane; forwards every commit via a typed signal."""

    field_text_changed = Signal(str, str)
    field_focus_lost = Signal(str, str)
    field_boolean_changed = Signal(str, bool)
    field_enum_changed = Signal(str, str)
    field_chip_values_changed = Signal(str, tuple)  # field_name, tuple[str, ...]

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("task_editor.field_editor")
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        self._header_label = QLabel("")
        self._header_label.setObjectName("task_editor.field_editor.header")
        outer.addWidget(self._header_label)

        scroll = QScrollArea()
        scroll.setObjectName("task_editor.field_editor.scroll")
        scroll.setWidgetResizable(True)
        self._form_container = QWidget()
        self._form_layout = QVBoxLayout(self._form_container)
        scroll.setWidget(self._form_container)
        outer.addWidget(scroll)

    def apply(self, rows: tuple[FieldRowViewModel, ...], *, header_text: str) -> None:
        """Push the selected task's field rows and pane-head text (§3.5)."""
        self._header_label.setText(header_text)
        _clear_layout(self._form_layout)
        rows_by_name = {row.field_name: row for row in rows}
        grouped_names = {name for _, names in FIELD_GROUPS for name in names}
        for row in rows:
            if row.field_name not in grouped_names:
                self._form_layout.addWidget(self._build_row(row))
        for group_label, field_names in FIELD_GROUPS:
            section_rows = tuple(rows_by_name[name] for name in field_names if name in rows_by_name)
            if section_rows:
                self._form_layout.addWidget(self._build_group(group_label, section_rows))
        self._form_layout.addStretch()

    def _build_group(self, title: str, rows: tuple[FieldRowViewModel, ...]) -> QGroupBox:
        box = QGroupBox(title)
        box.setCheckable(True)
        box.setChecked(True)
        box_layout = QVBoxLayout(box)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        for row in rows:
            content_layout.addWidget(self._build_row(row))
        box_layout.addWidget(content)
        box.toggled.connect(content.setVisible)
        return box

    def _build_row(self, row: FieldRowViewModel) -> QWidget:
        container = QWidget()
        container.setObjectName(f"task_editor.field_editor.row.{row.field_name}")
        layout = QVBoxLayout(container)

        label_row = QHBoxLayout()
        label = QLabel(f"{row.label} *" if row.is_required else row.label)
        font = label.font()
        font.setBold(row.is_required)
        label.setFont(font)
        label_row.addWidget(label)

        help_button = QToolButton()
        help_button.setObjectName(f"{row.field_name}_help_button")
        help_button.setText("?")
        help_button.setAccessibleName(f"Help: {row.label}")
        help_button.setToolTip("About this field")
        help_button.clicked.connect(partial(self._show_help, row.label, row.help_text))
        label_row.addWidget(help_button)
        label_row.addStretch()
        layout.addLayout(label_row)

        hint_label = QLabel(row.format_hint)
        hint_label.setObjectName(f"task_editor.field_editor.row.{row.field_name}.hint")
        layout.addWidget(hint_label)

        control = self._build_control(row)
        control.setAccessibleName(row.label)
        layout.addWidget(control)

        strip = QLabel(row.validation_message or _STATE_LABEL[row.validation_state])
        strip.setObjectName(f"task_editor.field_editor.row.{row.field_name}.strip")
        layout.addWidget(strip)
        return container

    def _show_help(self, label: str, help_text: str) -> None:
        QMessageBox.information(self, label, help_text)

    def _build_control(self, row: FieldRowViewModel) -> QWidget:
        if row.control_kind is FieldControlKind.BOOLEAN:
            return self._build_boolean_control(row)
        if row.control_kind is FieldControlKind.ENUM:
            return self._build_enum_control(row)
        if row.control_kind is FieldControlKind.CHIP_LIST:
            return self._build_chip_control(row)
        if row.control_kind is FieldControlKind.LONG_TEXT:
            return self._build_long_text_control(row)
        return self._build_short_text_control(row)

    def _build_short_text_control(self, row: FieldRowViewModel) -> QWidget:
        control = _FocusOutLineEdit()
        control.setObjectName(f"task_editor.field_editor.control.{row.field_name}")
        control.setText(row.value)
        control.textChanged.connect(partial(self._on_text_changed, row.field_name))
        control.focus_lost.connect(partial(self._on_line_focus_lost, row.field_name, control))
        return control

    def _build_long_text_control(self, row: FieldRowViewModel) -> QWidget:
        control = _FocusOutPlainTextEdit()
        control.setObjectName(f"task_editor.field_editor.control.{row.field_name}")
        control.setPlainText(row.value)
        control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if row.field_name == _MONOSPACE_FIELD:
            control.setFont(monospace_font())
        control.textChanged.connect(partial(self._on_plain_text_changed, row.field_name, control))
        control.focus_lost.connect(partial(self._on_plain_focus_lost, row.field_name, control))
        return control

    def _build_enum_control(self, row: FieldRowViewModel) -> QWidget:
        control = QComboBox()
        control.setObjectName(f"task_editor.field_editor.control.{row.field_name}")
        control.addItems([member.value for member in Difficulty])
        control.setCurrentText(row.value or Difficulty.MEDIUM.value)
        control.currentTextChanged.connect(partial(self.field_enum_changed.emit, row.field_name))
        return control

    def _build_boolean_control(self, row: FieldRowViewModel) -> QWidget:
        control = QCheckBox()
        control.setObjectName(f"task_editor.field_editor.control.{row.field_name}")
        control.setChecked(row.value == _TRUE_STR)
        control.toggled.connect(partial(self.field_boolean_changed.emit, row.field_name))
        return control

    def _build_chip_control(self, row: FieldRowViewModel) -> QWidget:
        control = _ChipInputWidget()
        control.setObjectName(f"task_editor.field_editor.control.{row.field_name}")
        control.set_values(row.chip_values)
        control.values_changed.connect(partial(self.field_chip_values_changed.emit, row.field_name))
        return control

    def _on_text_changed(self, field_name: str, text: str) -> None:
        self.field_text_changed.emit(field_name, text)

    def _on_line_focus_lost(self, field_name: str, control: QLineEdit) -> None:
        self.field_focus_lost.emit(field_name, control.text())

    def _on_plain_text_changed(self, field_name: str, control: QPlainTextEdit) -> None:
        self.field_text_changed.emit(field_name, control.toPlainText())

    def _on_plain_focus_lost(self, field_name: str, control: QPlainTextEdit) -> None:
        self.field_focus_lost.emit(field_name, control.toPlainText())
