"""The Editor Toolbar -- Open File/Open Folder/New File/Save/Save All/Reload/View
YAML, and the aggregate validation pill (STORY-068; ``description.md`` §3.2).

Save, Save All, and View YAML are permanent members of the fixed toolbar row but are
not wired to a working action this story (STORY-069's job) -- per this story's design
decision they render disabled with an explanatory tooltip rather than being omitted,
since they are fixed, permanent toolbar members per the spec's layout, unlike the
Files-pane context-menu items STORY-068 omits outright (see the story's Notes).
"""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ollama_llm_bench.ui.task_editor.models import ToolbarViewModel, ValidationState

__all__: list[str] = ["EditorToolbar"]

_NOT_YET_AVAILABLE_TOOLTIP = "Not yet available -- delivered by a follow-up story."
_NO_FILE_OPEN_TEXT = "no file open"
_RELOAD_DISABLED_TOOLTIP = "No active file to reload, or the active file has unsaved edits."
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
        layout.addWidget(self.open_file_button)

        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.setObjectName("task_editor.toolbar.open_folder")
        layout.addWidget(self.open_folder_button)

        self.new_file_button = QPushButton("New File")
        self.new_file_button.setObjectName("task_editor.toolbar.new_file")
        layout.addWidget(self.new_file_button)

        self._save_button = QPushButton("Save")
        self._save_button.setObjectName("task_editor.toolbar.save")
        self._save_button.setEnabled(False)
        self._save_button.setToolTip(_NOT_YET_AVAILABLE_TOOLTIP)
        layout.addWidget(self._save_button)

        self._save_all_button = QPushButton("Save All (0)")
        self._save_all_button.setObjectName("task_editor.toolbar.save_all")
        self._save_all_button.setEnabled(False)
        self._save_all_button.setToolTip(_NOT_YET_AVAILABLE_TOOLTIP)
        layout.addWidget(self._save_all_button)

        self.reload_button = QPushButton("Reload")
        self.reload_button.setObjectName("task_editor.toolbar.reload")
        self.reload_button.setEnabled(False)
        layout.addWidget(self.reload_button)

        self._view_yaml_button = QPushButton("View YAML")
        self._view_yaml_button.setObjectName("task_editor.toolbar.view_yaml")
        self._view_yaml_button.setEnabled(False)
        self._view_yaml_button.setToolTip(_NOT_YET_AVAILABLE_TOOLTIP)
        layout.addWidget(self._view_yaml_button)

        layout.addStretch()

        self._validation_pill = QLabel(_NO_FILE_OPEN_TEXT)
        self._validation_pill.setObjectName("task_editor.toolbar.validation_pill")
        layout.addWidget(self._validation_pill)

    def apply(self, toolbar_state: ToolbarViewModel, *, is_empty: bool) -> None:
        """Push the toolbar's render state (§3.2).

        Args:
            toolbar_state: The computed toolbar view-model slice.
            is_empty: Whether the workspace currently holds no open buffers.
        """
        self.reload_button.setEnabled(toolbar_state.reload_enabled)
        self.reload_button.setToolTip(
            "" if toolbar_state.reload_enabled else _RELOAD_DISABLED_TOOLTIP
        )
        self._save_all_button.setText(f"Save All ({toolbar_state.save_all_count})")
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
