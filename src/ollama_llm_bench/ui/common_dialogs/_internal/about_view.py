"""``AboutDialog`` -- the read-only application-identity modal (STORY-070-AC-1, AC-2, AC-7).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/about_dialog.md``
§4 (identity block), §5 (paths block), §6 (folder actions), §7-§8 (default state,
button behaviour), §11 (edge cases EC-AB-2, EC-AB-3, EC-AB-7). Pure presentation
-- persists nothing; every action keeps the dialog open (§9 state machine). The
dialog emits a ``GlobalMessageEvent`` confirmation/failure toast for its
clipboard/file-manager/browser actions (§6.1, §8, §11).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
import structlog

from ollama_llm_bench.adapters.clipboard import Clipboard
from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.backend.errors import OsAdapterError
from ollama_llm_bench.backend.events import SIGNAL_GLOBAL_MESSAGE, EventBus, GlobalMessageEvent
from ollama_llm_bench.ui.common_dialogs._internal.theme_lookup import monospace_font
from ollama_llm_bench.ui.common_dialogs.models import AboutDialogViewModel
from ollama_llm_bench.ui.shared import make_dialog_close_button

__all__: list[str] = ["AboutDialog"]

logger = structlog.get_logger(__name__)

_PATH_LABEL_MAX_WIDTH_PX = 320
_COPY_PATH_TOOLTIP = "Copy the application data folder path"
_OPEN_FOLDER_TOOLTIP = "Open the application data folder"
_PATH_COPIED_MESSAGE = "Path copied."
_COULD_NOT_COPY_PATH_MESSAGE = "Could not copy the path."
_COULD_NOT_OPEN_FOLDER_MESSAGE = "Could not open the folder."
_COULD_NOT_OPEN_REPOSITORY_LINK_MESSAGE = "Could not open the repository link."


class AboutDialog(QDialog):
    """The About dialog: identity block, GitHub link, data-folder path row."""

    def __init__(
        self,
        *,
        clipboard: Clipboard,
        file_system_actions: FileSystemActions,
        event_bus: EventBus,
        view_model: AboutDialogViewModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("common_dialogs.about")
        self.setWindowTitle(view_model.app_name)
        self._clipboard = clipboard
        self._file_system_actions = file_system_actions
        self._event_bus = event_bus
        self._data_folder_path = view_model.data_folder_path
        self._build_ui(view_model)
        logger.debug("about_dialog_constructed", data_folder_path=view_model.data_folder_path)

    def _build_ui(self, view_model: AboutDialogViewModel) -> None:
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        layout.addWidget(self._build_identity_block(view_model))
        layout.addWidget(self._build_path_row(view_model.data_folder_path))
        layout.addLayout(self._build_footer())

    def _build_identity_block(self, view_model: AboutDialogViewModel) -> QWidget:
        block = QWidget()
        block_layout = QVBoxLayout(block)
        block_layout.setContentsMargins(0, 0, 0, 0)

        name_label = QLabel(view_model.app_name)
        name_label.setObjectName("common_dialogs.about.app_name")
        name_label.setProperty("role", "heading")
        block_layout.addWidget(name_label)

        if view_model.version is not None:
            version_label = QLabel(view_model.version)
            version_label.setObjectName("common_dialogs.about.version")
            version_label.setProperty("role", "muted-caption")
            block_layout.addWidget(version_label)

        description_label = QLabel(view_model.description)
        description_label.setObjectName("common_dialogs.about.description")
        description_label.setProperty("role", "muted-caption")
        description_label.setWordWrap(True)
        block_layout.addWidget(description_label)

        self._repository_link = QLabel('<a href="repository">Project on GitHub</a>')
        self._repository_link.setObjectName("common_dialogs.about.repository_link")
        self._repository_link.setAccessibleName("Project on GitHub")
        self._repository_link.setToolTip("Open the project's GitHub repository in your browser")
        self._repository_link.setOpenExternalLinks(False)
        self._repository_link.linkActivated.connect(
            lambda _href: self._on_repository_link_activated(view_model.repository_url)
        )
        block_layout.addWidget(self._repository_link)
        return block

    def _build_path_row(self, data_folder_path: str) -> QWidget:
        row = QWidget()
        row.setObjectName("common_dialogs.about.path_row")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel("Application data folder")
        row_layout.addWidget(label)

        self._path_label = QLabel(
            _elide_path(data_folder_path, max_width_px=_PATH_LABEL_MAX_WIDTH_PX)
        )
        self._path_label.setObjectName("common_dialogs.about.path_display")
        self._path_label.setProperty("role", "monospace")
        self._path_label.setFont(monospace_font())
        self._path_label.setToolTip(data_folder_path)
        row_layout.addWidget(self._path_label, stretch=1)

        self.copy_path_button = QToolButton()
        self.copy_path_button.setObjectName("copy_data_folder_path_button")
        self.copy_path_button.setAccessibleName("Copy application data folder path")
        self.copy_path_button.setProperty("role", "icon-button")
        self.copy_path_button.setText("⧉")
        self.copy_path_button.setToolTip(_COPY_PATH_TOOLTIP)
        self.copy_path_button.setFixedSize(28, 28)
        self.copy_path_button.clicked.connect(self._on_copy_path_clicked)
        row_layout.addWidget(self.copy_path_button)

        self.open_folder_button = QToolButton()
        self.open_folder_button.setObjectName("open_data_folder_button")
        self.open_folder_button.setAccessibleName("Open application data folder")
        self.open_folder_button.setProperty("role", "icon-button")
        self.open_folder_button.setText("📂")
        self.open_folder_button.setToolTip(_OPEN_FOLDER_TOOLTIP)
        self.open_folder_button.setFixedSize(28, 28)
        self.open_folder_button.clicked.connect(self._on_open_folder_clicked)
        row_layout.addWidget(self.open_folder_button)
        return row

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.addStretch()
        self.close_button = make_dialog_close_button()
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        return footer

    def _on_copy_path_clicked(self) -> None:
        logger.debug("about_dialog_copy_path_clicked")
        try:
            self._clipboard.copy_text(self._data_folder_path)
        except OsAdapterError as exc:
            logger.warning(
                "about_dialog_copy_path_failed",
                data_folder_path=self._data_folder_path,
                error=str(exc),
            )
            self._emit_toast(_COULD_NOT_COPY_PATH_MESSAGE, severity="error")
            return
        self._emit_toast(_PATH_COPIED_MESSAGE, severity="info")

    def _on_open_folder_clicked(self) -> None:
        logger.debug("about_dialog_open_folder_clicked")
        try:
            self._file_system_actions.open_in_file_manager(self._data_folder_path)
        except OsAdapterError as exc:
            logger.warning(
                "about_dialog_open_folder_failed",
                data_folder_path=self._data_folder_path,
                error=str(exc),
            )
            self._emit_toast(_COULD_NOT_OPEN_FOLDER_MESSAGE, severity="error")

    def _on_repository_link_activated(self, repository_url: str) -> None:
        logger.debug("about_dialog_repository_link_activated", repository_url=repository_url)
        try:
            self._file_system_actions.open_url(repository_url)
        except OsAdapterError as exc:
            logger.warning(
                "about_dialog_repository_link_failed",
                repository_url=repository_url,
                error=str(exc),
            )
            self._emit_toast(_COULD_NOT_OPEN_REPOSITORY_LINK_MESSAGE, severity="error")

    def _emit_toast(self, text: str, *, severity: str) -> None:
        self._event_bus.emit(
            SIGNAL_GLOBAL_MESSAGE, GlobalMessageEvent(text=text, severity=severity)
        )


def _elide_path(path: str, *, max_width_px: int) -> str:
    """Elide ``path`` with a middle ellipsis once it exceeds ``max_width_px``
    (about_dialog.md §5, EC-AB-4). The hover tooltip always carries the full,
    untruncated path; only the visible label text is shortened here."""
    metrics = QFontMetrics(QLabel().font())
    return metrics.elidedText(path, Qt.TextElideMode.ElideMiddle, max_width_px)
