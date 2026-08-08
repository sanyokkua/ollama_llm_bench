"""``GeneralTabView`` -- the passive General tab: a scrollable column of
sections, one control per ``FIELD_REGISTRY`` entry, plus the Storage
section's read-only app-data path/Copy/Open-folder actions and the Logging
sections' Open-folder actions (``description.md`` §4).

A passive ``QWidget``: renders the ``GeneralFieldState`` tuple it is given and
emits Qt signals on user interaction. Imports no Gateway, no reactive store,
and no ``Clipboard``/``FileSystemActions`` -- those OS-integration
collaborators are wired by the *parent* ``SettingsController`` (Task 9), which
already retains them; this view only emits the four dedicated action
signals (the passive-View rule).
"""

import functools
from typing import cast

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.domain import SettingKey
from ollama_llm_bench.ui.settings_dialog._internal.general_tab.field_binders import (
    FIELD_REGISTRY,
    ControlKind,
    FieldSpec,
    GeneralSection,
)
from ollama_llm_bench.ui.settings_dialog.models import GeneralFieldState

__all__: list[str] = ["GeneralTabView"]

_SECTION_TITLES: dict[GeneralSection, str] = {
    GeneralSection.INFERENCE: "Inference",
    GeneralSection.BENCHMARK_EVENTS: "Benchmark Events",
    GeneralSection.EVALUATION: "Evaluation",
    GeneralSection.JUDGE_AND_EMBEDDING_TIMEOUTS: "Judge timeouts and embedding timeout",
    GeneralSection.RUN_LEVEL_ANALYSIS: "Run-level analysis",
    GeneralSection.EMBEDDING_MODELS: "Embedding Models",
    GeneralSection.DISPLAY: "Display",
    GeneralSection.LOGGING_RUN: "Logging — Run Logs",
    GeneralSection.LOGGING_APP: "Logging — App Logs",
    GeneralSection.TASK_EDITOR: "Task Editor",
}

# The Open-folder action appended at the end of a section's field rows
# (§4.7, §4.8) -- (button label, object-name/signal-attribute stem).
_TRAILING_BUTTONS: dict[GeneralSection, tuple[str, str]] = {
    GeneralSection.LOGGING_RUN: ("Open Run Logs folder", "open_run_logs_folder"),
    GeneralSection.LOGGING_APP: ("Open App Logs folder", "open_app_logs_folder"),
}

_INT_MAX_FALLBACK = 2_147_483_647
_FLOAT_MAX_FALLBACK = 1_000_000.0


def _section_order() -> tuple[GeneralSection, ...]:
    seen: list[GeneralSection] = []
    for spec in FIELD_REGISTRY:
        if spec.section not in seen:
            seen.append(spec.section)
    return tuple(seen)


class GeneralTabView(QWidget):
    """Passive General tab: scrollable sections, Storage row, Open-folder actions."""

    value_edited = Signal(str, str)
    copy_app_data_path_clicked = Signal()
    open_app_folder_clicked = Signal()
    open_run_logs_folder_clicked = Signal()
    open_app_logs_folder_clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("settings_dialog.general_tab")
        self._controls: dict[SettingKey, QWidget] = {}
        self._app_data_path_label = QLabel("")
        self._build_ui()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        scroll_area = QScrollArea()
        scroll_area.setObjectName("settings_dialog.general_tab.scroll_area")
        scroll_area.setWidgetResizable(True)

        column = QWidget()
        column_layout = QVBoxLayout(column)
        for section in _section_order():
            column_layout.addWidget(self._build_section_group(section))
        column_layout.addWidget(self._build_storage_group())
        column_layout.addStretch()

        scroll_area.setWidget(column)
        outer_layout.addWidget(scroll_area)

    def _build_section_group(self, section: GeneralSection) -> QGroupBox:
        group = QGroupBox(_SECTION_TITLES[section])
        group_layout = QVBoxLayout(group)
        for spec in FIELD_REGISTRY:
            if spec.section is section:
                group_layout.addWidget(self._build_field_row(spec))
        trailing = _TRAILING_BUTTONS.get(section)
        if trailing is not None:
            label, signal_stem = trailing
            button = QPushButton(label)
            button.setObjectName(f"settings_dialog.general_tab.{signal_stem}")
            button.setAccessibleName(label)
            button.clicked.connect(getattr(self, f"{signal_stem}_clicked"))
            group_layout.addWidget(button)
        return group

    def _build_field_row(self, spec: FieldSpec) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(QLabel(spec.label))
        control = self._build_control(spec)
        control.setObjectName(spec.setting_key)
        control.setAccessibleName(spec.label)
        self._controls[spec.setting_key] = control
        row_layout.addWidget(control, 1)
        return row

    def _build_control(self, spec: FieldSpec) -> QWidget:
        if spec.kind is ControlKind.BOOL:
            return self._build_bool_control(spec.setting_key)
        if spec.kind is ControlKind.ENUM:
            return self._build_enum_control(spec)
        if spec.kind is ControlKind.INT:
            return self._build_int_control(spec)
        if spec.kind is ControlKind.FLOAT:
            return self._build_float_control(spec)
        return self._build_text_control(spec.setting_key)

    def _build_bool_control(self, setting_key: SettingKey) -> QCheckBox:
        checkbox = QCheckBox()
        checkbox.setObjectName(setting_key)
        checkbox.toggled.connect(functools.partial(self._on_bool_changed, setting_key))
        return checkbox

    def _build_enum_control(self, spec: FieldSpec) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName(spec.setting_key)
        combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        combo.addItems(list(spec.enum_choices))
        combo.currentTextChanged.connect(functools.partial(self._on_text_changed, spec.setting_key))
        return combo

    def _build_int_control(self, spec: FieldSpec) -> QSpinBox:
        spin = QSpinBox()
        spin.setObjectName(spec.setting_key)
        spin.setRange(
            spec.int_min if spec.int_min is not None else 0, spec.int_max or _INT_MAX_FALLBACK
        )
        spin.valueChanged.connect(functools.partial(self._on_int_changed, spec.setting_key))
        return spin

    def _build_float_control(self, spec: FieldSpec) -> QDoubleSpinBox:
        dspin = QDoubleSpinBox()
        dspin.setObjectName(spec.setting_key)
        dspin.setDecimals(2)
        dspin.setRange(
            spec.float_min if spec.float_min is not None else 0.0,
            spec.float_max or _FLOAT_MAX_FALLBACK,
        )
        dspin.valueChanged.connect(functools.partial(self._on_float_changed, spec.setting_key))
        return dspin

    def _build_text_control(self, setting_key: SettingKey) -> QLineEdit:
        line_edit = QLineEdit()
        line_edit.setObjectName(setting_key)
        line_edit.textEdited.connect(functools.partial(self._on_text_changed, setting_key))
        return line_edit

    def _build_storage_group(self) -> QGroupBox:
        group = QGroupBox("Storage")
        layout = QVBoxLayout(group)

        path_row = QWidget()
        path_row_layout = QHBoxLayout(path_row)
        path_row_layout.setContentsMargins(0, 0, 0, 0)
        self._app_data_path_label.setObjectName("settings_dialog.general_tab.app_data_path")
        path_row_layout.addWidget(self._app_data_path_label, 1)
        copy_button = QPushButton("Copy")
        copy_button.setObjectName("settings_dialog.general_tab.copy_app_data_path")
        copy_button.setAccessibleName("Copy application data folder path")
        copy_button.clicked.connect(self.copy_app_data_path_clicked)
        path_row_layout.addWidget(copy_button)
        layout.addWidget(path_row)

        open_app_folder_button = QPushButton("Open App folder")
        open_app_folder_button.setObjectName("settings_dialog.general_tab.open_app_folder")
        open_app_folder_button.setAccessibleName("Open App folder")
        open_app_folder_button.clicked.connect(self.open_app_folder_clicked)
        layout.addWidget(open_app_folder_button)
        return group

    def _on_bool_changed(self, setting_key: SettingKey, checked: bool) -> None:  # noqa: FBT001  # Qt's own toggled(bool) signal signature
        self.value_edited.emit(setting_key, "true" if checked else "false")

    def _on_text_changed(self, setting_key: SettingKey, text: str) -> None:
        self.value_edited.emit(setting_key, text)

    def _on_int_changed(self, setting_key: SettingKey, value: int) -> None:
        self.value_edited.emit(setting_key, str(value))

    def _on_float_changed(self, setting_key: SettingKey, value: float) -> None:
        self.value_edited.emit(setting_key, str(value))

    def set_field_states(self, states: tuple[GeneralFieldState, ...]) -> None:
        """Render the working copy's current values (STORY-067-AC-1)."""
        specs_by_key = {spec.setting_key: spec for spec in FIELD_REGISTRY}
        for state in states:
            spec = specs_by_key.get(state.setting_key)
            control = self._controls.get(state.setting_key)
            if spec is None or control is None:
                continue
            self._apply_value(spec, control, state.value)
            control.setProperty("hasError", state.has_error)
            style = control.style()
            if style is not None:
                style.unpolish(control)
                style.polish(control)

    def _apply_value(self, spec: FieldSpec, control: QWidget, value: str) -> None:
        with QSignalBlocker(control):
            if spec.kind is ControlKind.BOOL:
                cast("QCheckBox", control).setChecked(value.strip().lower() == "true")
            elif spec.kind is ControlKind.ENUM:
                cast("QComboBox", control).setCurrentText(value)
            elif spec.kind is ControlKind.INT:
                cast("QSpinBox", control).setValue(int(value) if value.strip() else 0)
            elif spec.kind is ControlKind.FLOAT:
                cast("QDoubleSpinBox", control).setValue(float(value) if value.strip() else 0.0)
            else:
                cast("QLineEdit", control).setText(value)

    def set_app_data_path(self, path: str) -> None:
        """Render the Storage section's resolved, read-only app-data path."""
        self._app_data_path_label.setText(path)
