"""The Editor Toolbar -- Open File/Open Folder/New File/Save/Save All/Reload/View
YAML, and the aggregate validation pill (STORY-068, STORY-069; ``description.md``
§3.2).
"""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ollama_llm_bench.ui.task_editor.models import ToolbarViewModel, ValidationState

__all__: list[str] = ["EditorToolbar"]

_NO_FILE_OPEN_TEXT = "no file open"
_RELOAD_DISABLED_TOOLTIP = "No active file to reload."
_SAVE_DISABLED_TOOLTIP = "The active file has no unsaved changes, or has a hard error."
_SAVE_ALL_DISABLED_TOOLTIP = "No dirty file is free of hard errors."
_VIEW_YAML_SHOWN_TEXT = "View YAML (on)"
_VIEW_YAML_HIDDEN_TEXT = "View YAML"
_AGGREGATE_LABEL_BY_STATE: dict[ValidationState, str] = {
    ValidationState.CLEAN: "{count} tasks, 0 errors",
    ValidationState.INFO: "{count} tasks, 0 errors",
    ValidationState.WARNING: "{count} tasks, {warnings} warning(s)",
    ValidationState.ERROR: "{count} tasks, {errors} error(s)",
}


class EditorToolbar(QWidget):
    """Passive toolbar row; forwards every enabled click to its controller."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("task_editor.toolbar")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)

        self.open_file_button = QPushButton("Open File")
        self.open_file_button.setObjectName("task_editor.toolbar.open_file")
        self.open_file_button.setAccessibleName("Open File")
        layout.addWidget(self.open_file_button)

        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.setObjectName("task_editor.toolbar.open_folder")
        self.open_folder_button.setAccessibleName("Open Folder")
        layout.addWidget(self.open_folder_button)

        self.new_file_button = QPushButton("New File")
        self.new_file_button.setObjectName("task_editor.toolbar.new_file")
        self.new_file_button.setAccessibleName("New File")
        layout.addWidget(self.new_file_button)

        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("task_editor.toolbar.save")
        self.save_button.setAccessibleName("Save")
        layout.addWidget(self.save_button)

        self.save_all_button = QPushButton("Save All (0)")
        self.save_all_button.setObjectName("task_editor.toolbar.save_all")
        self.save_all_button.setAccessibleName("Save all files")
        layout.addWidget(self.save_all_button)

        self.reload_button = QPushButton("Reload")
        self.reload_button.setObjectName("task_editor.toolbar.reload")
        self.reload_button.setAccessibleName("Reload")
        self.reload_button.setEnabled(False)
        layout.addWidget(self.reload_button)

        self.view_yaml_button = QPushButton(_VIEW_YAML_HIDDEN_TEXT)
        self.view_yaml_button.setObjectName("task_editor.toolbar.view_yaml")
        self.view_yaml_button.setAccessibleName("View YAML")
        layout.addWidget(self.view_yaml_button)

        layout.addStretch()

        self._validation_pill = QLabel(_NO_FILE_OPEN_TEXT)
        self._validation_pill.setObjectName("task_editor.toolbar.validation_pill")
        layout.addWidget(self._validation_pill)

    def apply(
        self, toolbar_state: ToolbarViewModel, *, is_empty: bool, preview_shown: bool
    ) -> None:
        """Push the toolbar's render state (§3.2).

        Args:
            toolbar_state: The computed toolbar view-model slice.
            is_empty: Whether the workspace currently holds no open buffers.
            preview_shown: The YAML-preview toggle state, for the View YAML
                button's active-dot text (§3.6).
        """
        self.reload_button.setEnabled(toolbar_state.reload_enabled)
        self.reload_button.setToolTip(
            "" if toolbar_state.reload_enabled else _RELOAD_DISABLED_TOOLTIP
        )
        self.save_button.setEnabled(toolbar_state.save_enabled)
        self.save_button.setToolTip("" if toolbar_state.save_enabled else _SAVE_DISABLED_TOOLTIP)
        self.save_all_button.setText(f"Save All ({toolbar_state.save_all_count})")
        self.save_all_button.setEnabled(toolbar_state.save_all_enabled)
        self.save_all_button.setToolTip(
            "" if toolbar_state.save_all_enabled else _SAVE_ALL_DISABLED_TOOLTIP
        )
        self.view_yaml_button.setText(
            _VIEW_YAML_SHOWN_TEXT if preview_shown else _VIEW_YAML_HIDDEN_TEXT
        )
        if is_empty:
            self._validation_pill.setText(_NO_FILE_OPEN_TEXT)
            return
        template = _AGGREGATE_LABEL_BY_STATE[toolbar_state.aggregate_state]
        self._validation_pill.setText(
            template.format(
                count=toolbar_state.aggregate_task_count,
                warnings=toolbar_state.aggregate_warning_count,
                errors=toolbar_state.aggregate_error_count,
            )
        )
