"""``TaskEditorView`` -- the passive Task Editor workspace root widget (STORY-068,
STORY-069).

Composes the fixed toolbar with the Empty-state drop target / recent-files list and
the With-files body: Files pane, Tasks pane, Field-editor pane, and the YAML preview
panel (shown only when toggled, §2.1). Imports no adapter Gateway, no reactive store,
and no ``ollama_llm_bench.backend.*`` symbol (the passive-View rule).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.ui.task_editor._internal.field_editor import FieldEditorWidget
from ollama_llm_bench.ui.task_editor._internal.files_pane import FilesPaneWidget
from ollama_llm_bench.ui.task_editor._internal.tasks_pane import TasksPaneWidget
from ollama_llm_bench.ui.task_editor._internal.toolbar import EditorToolbar
from ollama_llm_bench.ui.task_editor._internal.yaml_preview import YamlPreviewWidget
from ollama_llm_bench.ui.task_editor.models import TaskEditorViewModel, ValidationState

__all__: list[str] = ["TaskEditorView"]

_DROP_TARGET_TEXT = "Drop YAML files or folders here"
_NO_RECENT_FILES_TEXT = "No recent files"


def _field_editor_header(view_model: TaskEditorViewModel) -> str:
    """Build "Editing: <task_id> (K of N)" plus a warning/error suffix (§3.5)."""
    index = view_model.active_task_index
    if index is None or not (0 <= index < len(view_model.tasks)):
        return ""
    task_row = view_model.tasks[index]
    header = f"Editing: {task_row.task_id} ({index + 1} of {len(view_model.tasks)})"
    errors = sum(
        1 for row in view_model.field_rows if row.validation_state is ValidationState.ERROR
    )
    warnings = sum(
        1 for row in view_model.field_rows if row.validation_state is ValidationState.WARNING
    )
    if errors:
        return f"{header} -- {errors} error(s)"
    if warnings:
        return f"{header} -- {warnings} warning(s)"
    return header


def _active_file_has_hard_error(view_model: TaskEditorViewModel) -> bool:
    index = view_model.active_file_index
    if index is None or not (0 <= index < len(view_model.files)):
        return False
    return view_model.files[index].validation_state is ValidationState.ERROR


class TaskEditorView(QWidget):
    """Passive Task Editor workspace root; forwards every user action via signals."""

    open_file_clicked = Signal()
    open_folder_clicked = Signal()
    new_file_clicked = Signal()
    reload_clicked = Signal()
    recent_file_clicked = Signal(str)
    files_dropped = Signal(object)
    file_row_selected = Signal(int)
    close_requested = Signal(int)
    close_others_requested = Signal(int)
    reveal_requested = Signal(int)
    reload_from_disk_requested = Signal(int)
    task_row_selected = Signal(int)
    add_task_clicked = Signal()
    duplicate_task_clicked = Signal(int)
    remove_tasks_clicked = Signal(object)
    move_up_clicked = Signal(int)
    move_down_clicked = Signal(int)
    save_clicked = Signal()
    save_all_clicked = Signal()
    view_yaml_toggled = Signal()
    copy_yaml_clicked = Signal()
    field_text_changed = Signal(str, str)
    field_focus_lost = Signal(str, str)
    field_boolean_changed = Signal(str, bool)
    field_enum_changed = Signal(str, str)
    field_chip_values_changed = Signal(str, tuple)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("task_editor.view")
        self.setAcceptDrops(True)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._toolbar = EditorToolbar()
        self._toolbar.open_file_button.clicked.connect(self.open_file_clicked.emit)
        self._toolbar.open_folder_button.clicked.connect(self.open_folder_clicked.emit)
        self._toolbar.new_file_button.clicked.connect(self.new_file_clicked.emit)
        self._toolbar.reload_button.clicked.connect(self.reload_clicked.emit)
        self._toolbar.save_button.clicked.connect(self.save_clicked.emit)
        self._toolbar.save_all_button.clicked.connect(self.save_all_clicked.emit)
        self._toolbar.view_yaml_button.clicked.connect(self.view_yaml_toggled.emit)
        layout.addWidget(self._toolbar)

        self._stack = QStackedWidget()
        self._empty_state = self._build_empty_state()
        self._stack.addWidget(self._empty_state)
        self._with_files_body = self._build_with_files_body()
        self._stack.addWidget(self._with_files_body)
        layout.addWidget(self._stack)

    def _build_empty_state(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("task_editor.empty_state")
        empty_layout = QVBoxLayout(widget)

        drop_label = QLabel(_DROP_TARGET_TEXT)
        drop_label.setObjectName("task_editor.empty_state.drop_target")
        empty_layout.addWidget(drop_label)

        recent_label = QLabel("Recent files")
        recent_label.setObjectName("task_editor.empty_state.recent_files_label")
        empty_layout.addWidget(recent_label)

        self._recent_files_list = QListWidget()
        self._recent_files_list.setObjectName("task_editor.empty_state.recent_files")
        self._recent_files_list.itemActivated.connect(self._on_recent_file_activated)
        self._recent_files_list.itemClicked.connect(self._on_recent_file_activated)
        empty_layout.addWidget(self._recent_files_list)
        return widget

    def _build_with_files_body(self) -> QWidget:
        widget = QWidget()
        widget.setObjectName("task_editor.with_files_body")
        body_layout = QHBoxLayout(widget)

        splitter = QSplitter()
        self._files_pane = FilesPaneWidget()
        self._files_pane.row_selected.connect(self.file_row_selected.emit)
        self._files_pane.open_file_button.clicked.connect(self.open_file_clicked.emit)
        self._files_pane.open_folder_button.clicked.connect(self.open_folder_clicked.emit)
        self._files_pane.new_file_button.clicked.connect(self.new_file_clicked.emit)
        self._files_pane.files_dropped.connect(self.files_dropped.emit)
        self._files_pane.close_requested.connect(self.close_requested.emit)
        self._files_pane.close_others_requested.connect(self.close_others_requested.emit)
        self._files_pane.reveal_requested.connect(self.reveal_requested.emit)
        self._files_pane.reload_requested.connect(self.reload_from_disk_requested.emit)
        splitter.addWidget(self._files_pane)

        self._tasks_pane = TasksPaneWidget()
        self._tasks_pane.row_selected.connect(self.task_row_selected.emit)
        self._tasks_pane.add_task_clicked.connect(self.add_task_clicked.emit)
        self._tasks_pane.duplicate_task_clicked.connect(self.duplicate_task_clicked.emit)
        self._tasks_pane.remove_tasks_clicked.connect(self.remove_tasks_clicked.emit)
        self._tasks_pane.move_up_clicked.connect(self.move_up_clicked.emit)
        self._tasks_pane.move_down_clicked.connect(self.move_down_clicked.emit)
        splitter.addWidget(self._tasks_pane)

        self._field_editor = FieldEditorWidget()
        self._field_editor.field_text_changed.connect(self.field_text_changed.emit)
        self._field_editor.field_focus_lost.connect(self.field_focus_lost.emit)
        self._field_editor.field_boolean_changed.connect(self.field_boolean_changed.emit)
        self._field_editor.field_enum_changed.connect(self.field_enum_changed.emit)
        self._field_editor.field_chip_values_changed.connect(self.field_chip_values_changed.emit)
        splitter.addWidget(self._field_editor)

        self._yaml_preview = YamlPreviewWidget()
        self._yaml_preview.copy_clicked.connect(self.copy_yaml_clicked.emit)
        self._yaml_preview.setVisible(False)
        splitter.addWidget(self._yaml_preview)

        body_layout.addWidget(splitter)
        return widget

    def apply_view_model(self, view_model: TaskEditorViewModel) -> None:
        """Push the workspace's full render state (§4)."""
        self._toolbar.apply(
            view_model.toolbar_state,
            is_empty=view_model.is_empty,
            preview_shown=view_model.preview_shown,
        )
        self._stack.setCurrentWidget(
            self._empty_state if view_model.is_empty else self._with_files_body
        )
        self._files_pane.apply(view_model.files)
        self._tasks_pane.apply(view_model.tasks)
        self._field_editor.apply(
            view_model.field_rows, header_text=_field_editor_header(view_model)
        )
        self._yaml_preview.set_preview_text(view_model.preview_text)
        self._yaml_preview.set_save_disabled_note_visible(
            visible=_active_file_has_hard_error(view_model)
        )
        self._yaml_preview.setVisible(view_model.preview_shown)

    def set_preview_text(self, text: str) -> None:
        """Push a debounced live preview re-render, bypassing a full view-model
        push so an in-flight field edit is never disrupted (STORY-069-AC-5)."""
        self._yaml_preview.set_preview_text(text)

    def set_recent_files(self, paths: tuple[str, ...]) -> None:
        """Push the session-only recent-files list shown in the Empty state (§2.3)."""
        self._recent_files_list.clear()
        if not paths:
            placeholder = QListWidgetItem(_NO_RECENT_FILES_TEXT)
            placeholder.setFlags(placeholder.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self._recent_files_list.addItem(placeholder)
            return
        for path in paths:
            self._recent_files_list.addItem(QListWidgetItem(path))

    def _on_recent_file_activated(self, item: QListWidgetItem) -> None:
        text = item.text()
        if text == _NO_RECENT_FILES_TEXT:
            return
        self.recent_file_clicked.emit(text)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = tuple(url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile())
        if paths:
            self.files_dropped.emit(paths)
        event.acceptProposedAction()
