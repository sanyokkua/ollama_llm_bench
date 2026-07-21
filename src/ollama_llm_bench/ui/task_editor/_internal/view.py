"""``TaskEditorView`` -- the passive Task Editor workspace root widget (STORY-068).

Composes the fixed toolbar with the Empty-state drop target / recent-files list and
the With-files two-pane body (Files pane, Tasks pane -- the Field-editor pane and the
YAML preview panel are STORY-069's scope, so the With-files body is two panes, not
the spec's eventual three/four). Imports no adapter Gateway, no reactive store, and no
``ollama_llm_bench.backend.*`` symbol (the passive-View rule).
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

from ollama_llm_bench.ui.task_editor._internal.files_pane import FilesPaneWidget
from ollama_llm_bench.ui.task_editor._internal.tasks_pane import TasksPaneWidget
from ollama_llm_bench.ui.task_editor._internal.toolbar import EditorToolbar
from ollama_llm_bench.ui.task_editor.models import TaskEditorViewModel

__all__: list[str] = ["TaskEditorView"]

_DROP_TARGET_TEXT = "Drop YAML files or folders here"
_NO_RECENT_FILES_TEXT = "No recent files"


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

        body_layout.addWidget(splitter)
        return widget

    def apply_view_model(self, view_model: TaskEditorViewModel) -> None:
        """Push the workspace's full render state (§4)."""
        self._toolbar.apply(view_model.toolbar_state, is_empty=view_model.is_empty)
        self._stack.setCurrentWidget(
            self._empty_state if view_model.is_empty else self._with_files_body
        )
        self._files_pane.apply(view_model.files)
        self._tasks_pane.apply(view_model.tasks)

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
