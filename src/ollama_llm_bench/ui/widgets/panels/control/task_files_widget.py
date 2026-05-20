"""TaskFilesWidget — self-contained task file / folder selection widget."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.ui.qt_classes.drag_drop_handler import DragDropHandler

_logger = logging.getLogger(__name__)

_YAML_FILTER = "YAML Files (*.yaml *.yml)"
_DROP_HINT_TEXT = "Drag & drop YAML task files or folders here"


class TaskFilesWidget(QWidget):
    """Widget for selecting and managing task file/folder paths.

    Displays a QListWidget of selected paths with drag-and-drop support,
    and buttons for adding files, adding folders, and removing entries.
    A drop hint label is shown when the list is empty.
    """

    tasks_changed = Signal()

    def __init__(self, *, parent: QWidget | None = None) -> None:
        """Initialize TaskFilesWidget.

        Args:
            parent: Optional parent widget for ownership management.
        """
        super().__init__(parent)
        self._task_paths: list[Path] = []

        self._create_widgets()
        self._configure_widgets()
        self._build_layout()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Widget creation
    # ------------------------------------------------------------------

    def _create_widgets(self) -> None:
        self._task_label = QLabel("Task Files")
        self._task_files_list = QListWidget()
        self._drop_hint_label = QLabel(_DROP_HINT_TEXT)
        self._stack = QStackedWidget()
        self._add_file_btn = QPushButton("Add File")
        self._add_folder_btn = QPushButton("Add Folder")
        self._remove_file_btn = QPushButton("Remove")
        self._drag_drop_handler = DragDropHandler(self)

    # ------------------------------------------------------------------
    # Widget configuration
    # ------------------------------------------------------------------

    def _configure_widgets(self) -> None:
        self._task_label.setProperty("role", "secondary")

        self._drop_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_hint_label.setProperty("role", "drop-zone")

        self._drag_drop_handler.install_on(self._task_files_list)

        self._add_file_btn.setProperty("size", "small")
        self._add_file_btn.setToolTip("Open a file picker to add one or more YAML task files.")

        self._add_folder_btn.setProperty("size", "small")
        self._add_folder_btn.setToolTip("Open a folder picker — all YAML files in the folder are added.")

        self._remove_file_btn.setProperty("size", "small")
        self._remove_file_btn.setToolTip("Remove the selected entry from the task file list.")

        self._task_files_list.setToolTip("Task files and folders queued for this run. Drag & drop YAML files here.")

    # ------------------------------------------------------------------
    # Layout assembly
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(3)
        btn_row.addWidget(self._add_file_btn)
        btn_row.addWidget(self._add_folder_btn)
        btn_row.addWidget(self._remove_file_btn)

        self._stack.addWidget(self._drop_hint_label)  # index 0 — shown when empty
        self._stack.addWidget(self._task_files_list)  # index 1 — shown when populated
        self._stack.setCurrentIndex(0)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(3)
        outer.addWidget(self._task_label)
        outer.addWidget(self._stack, stretch=1)
        outer.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._add_file_btn.clicked.connect(self._add_task_file_dialog)
        self._add_folder_btn.clicked.connect(self._add_task_folder_dialog)
        self._remove_file_btn.clicked.connect(self._remove_selected_task_file)
        self._drag_drop_handler.yaml_file_dropped.connect(self._add_task_file)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _add_task_file_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Select Task File", "", _YAML_FILTER)
        for path_str in paths:
            self._add_task_file(Path(path_str))

    def _add_task_folder_dialog(self) -> None:
        folder_str = QFileDialog.getExistingDirectory(self, "Select Task Folder")
        if not folder_str:
            return
        folder = Path(folder_str)
        for path in sorted(folder.glob("*.yaml")) + sorted(folder.glob("*.yml")):
            self._add_task_file(path)

    def _add_task_file(self, path: Path) -> None:
        if path in self._task_paths:
            _logger.debug("Duplicate task file ignored: %s", path)
            return
        self._task_paths.append(path)
        self._task_files_list.addItem(path.name)
        self._stack.setCurrentIndex(1)
        self.tasks_changed.emit()

    def _remove_selected_task_file(self) -> None:
        selected = self._task_files_list.selectedItems()
        for item in sorted(selected, key=lambda it: self._task_files_list.row(it), reverse=True):
            row = self._task_files_list.row(item)
            self._task_files_list.takeItem(row)
            del self._task_paths[row]
        if self._task_files_list.count() == 0:
            self._stack.setCurrentIndex(0)
        self.tasks_changed.emit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_task_paths(self) -> list[Path]:
        """Return the list of task file/folder paths currently in the list.

        Returns:
            List of Path objects for the selected task files and folders.
        """
        return list(self._task_paths)
