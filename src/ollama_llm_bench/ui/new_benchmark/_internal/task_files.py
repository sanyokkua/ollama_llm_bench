"""``TaskFilesSectionWidget`` -- the Task Files list (STORY-054-AC-4, AC-6).

Source of truth: ``02_New_Benchmark_Widget/description.md`` §5 (behaviour per
element), ``state_machine.md`` §4 (EmptyDropZone <-> Populated). Covers EC-TASK-1
(whole-file parse error -> inline error, no row), EC-TASK-3 (a malformed individual
task is already excluded by ``TaskFileLoader`` -- the badge reflects the surviving
count), EC-TASK-8 (an Add-Folder selection with no .yaml/.yml file -> toast, no row).
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import structlog

from ollama_llm_bench.adapters.native_pickers import (
    FilePickerOptions,
    FolderPickerOptions,
    NativePickers,
)
from ollama_llm_bench.adapters.workspace_controller import WorkspaceController, WorkspaceHint
from ollama_llm_bench.backend.errors import TaskFileError
from ollama_llm_bench.backend.task_files import TaskFileLoader
from ollama_llm_bench.ui.new_benchmark.models import TaskFileRowViewModel
from ollama_llm_bench.ui.shared import make_badge_label
from ollama_llm_bench.ui.shared.models import BadgeStatus
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

__all__: list[str] = ["TaskFilesSectionWidget"]

logger = structlog.get_logger(__name__)

_YAML_SUFFIXES = (".yaml", ".yml")


class TaskFilesSectionWidget(QWidget):
    """The Task Files section: drag-drop, Add File/Add Folder/Remove, per-file badge.

    ``theme_manager``/``platform_kind`` are optional keyword arguments: the real
    production wiring (Task 10/11) supplies both and each row shows a themed
    ``(N tasks)`` badge via ``make_badge_label``; a caller that omits them (as unit
    tests with no live ``ThemeManager`` do) still gets a fully functional row --
    the task count is folded into the row's plain text instead, so the widget
    never depends on a ``QApplication``-bound theme collaborator to be testable.
    """

    rows_changed = Signal(object)

    def __init__(
        self,
        *,
        task_file_loader: TaskFileLoader,
        native_pickers: NativePickers,
        workspace: WorkspaceController,
        theme_manager: ThemeManager | None = None,
        platform_kind: PlatformKind = PlatformKind.UNKNOWN,
    ) -> None:
        super().__init__()
        self.setObjectName("new_benchmark.task_files")
        self._loader = task_file_loader
        self._pickers = native_pickers
        self._workspace = workspace
        self._theme_manager = theme_manager
        self._platform_kind = platform_kind
        self._rows: dict[str, TaskFileRowViewModel] = {}
        self.last_inline_error: str | None = None
        self.last_toast_message: str | None = None
        self.setAcceptDrops(True)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._list = QListWidget()
        self._list.setObjectName("new_benchmark.task_files.list")
        layout.addWidget(self._list)

        button_row = QHBoxLayout()
        self._add_file_button = QPushButton("Add File")
        self._add_file_button.setProperty("role", "outlined-muted-button")
        self._add_file_button.clicked.connect(self._on_add_file_clicked)
        self._add_folder_button = QPushButton("Add Folder")
        self._add_folder_button.setProperty("role", "outlined-muted-button")
        self._add_folder_button.clicked.connect(self._on_add_folder_clicked)
        self._remove_button = QPushButton("Remove")
        self._remove_button.setProperty("role", "outlined-muted-button")
        self._remove_button.clicked.connect(self._on_remove_clicked)
        self._open_in_editor_button = QPushButton("Open in Task Editor")
        self._open_in_editor_button.setProperty("role", "outlined-muted-button")
        self._open_in_editor_button.clicked.connect(self._on_open_in_editor_clicked)
        for button in (
            self._add_file_button,
            self._add_folder_button,
            self._remove_button,
            self._open_in_editor_button,
        ):
            button_row.addWidget(button)
        layout.addLayout(button_row)

    @property
    def rows(self) -> tuple[TaskFileRowViewModel, ...]:
        """Every current Task Files row, in add order."""
        return tuple(self._rows.values())

    def _on_add_file_clicked(self) -> None:
        paths = self._pickers.open_file(
            FilePickerOptions(
                title="Add Task File", filters=("YAML (*.yaml *.yml)",), allow_multiple=True
            )
        )
        if paths:
            self._load_and_append(paths)

    def _on_add_folder_clicked(self) -> None:
        folder = self._pickers.open_folder(FolderPickerOptions(title="Add Task Folder"))
        if folder is not None:
            yaml_paths = tuple(
                str(p) for p in Path(folder).iterdir() if p.suffix.lower() in _YAML_SUFFIXES
            )
            self.add_folder_for_test(folder, yaml_paths)

    def _on_remove_clicked(self) -> None:
        selected = self._list.selectedItems()
        for item in selected:
            source_path: str = item.data(Qt.ItemDataRole.UserRole)
            self._rows.pop(source_path, None)
        self._refresh_list()
        self.rows_changed.emit(self.rows)

    def _on_open_in_editor_clicked(self) -> None:
        selected_paths = tuple(
            item.data(Qt.ItemDataRole.UserRole) for item in self._list.selectedItems()
        ) or tuple(self._rows)
        self._workspace.switch_to("task_editor", WorkspaceHint(open_paths=selected_paths))

    def add_files_for_test(self, paths: tuple[str, ...]) -> None:
        """Test helper: drive the same load-and-append path Add File/drop use."""
        self._load_and_append(paths)

    def add_folder_for_test(self, folder_path: str, yaml_paths: tuple[str, ...]) -> None:
        """Test helper: drive the same Add-Folder path a real folder pick uses."""
        if not yaml_paths:
            self.last_toast_message = "No YAML files found in the selected folder."
            logger.debug("task_files_add_folder_empty", folder_path=folder_path)
            return
        self._load_and_append(yaml_paths)

    def _load_and_append(self, paths: tuple[str, ...]) -> None:
        self.last_inline_error = None
        for source_path in paths:
            try:
                tasks = self._loader.load(source_path)
            except TaskFileError as exc:
                self.last_inline_error = exc.message
                logger.debug(
                    "task_files_load_rejected", source_path=source_path, reason=exc.message
                )
                continue
            file_name = Path(source_path).name
            self._rows[source_path] = TaskFileRowViewModel(
                source_path=source_path, file_name=file_name, task_count=len(tasks)
            )
            logger.debug("task_files_row_added", source_path=source_path, task_count=len(tasks))
        self._refresh_list()
        self.rows_changed.emit(self.rows)

    def _refresh_list(self) -> None:
        self._list.clear()
        for row in self._rows.values():
            item = QListWidgetItem(row.file_name)
            item.setData(Qt.ItemDataRole.UserRole, row.source_path)
            self._list.addItem(item)
            if self._theme_manager is None:
                item.setText(f"{row.file_name}  ({row.task_count} tasks)")
                continue
            badge = make_badge_label(
                status=BadgeStatus.INFO,
                text=f"({row.task_count} tasks)",
                theme_manager=self._theme_manager,
                platform_kind=self._platform_kind,
            )
            self._list.setItemWidget(item, badge)
