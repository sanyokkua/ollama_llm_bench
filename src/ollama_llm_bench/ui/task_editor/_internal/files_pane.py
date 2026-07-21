"""Files pane -- flat buffer list, per-file badges, drag-drop, context menu, footer
open/create controls, and the in-use-by-run marker (STORY-068; ``description.md``
§3.3, §7, §9 EC-TE-07).

The badge is rendered as a short text glyph (no colour channel) so the row's state is
legible with no ``ThemeManager`` collaborator -- ``TaskEditorCollaborators`` (STORY-068
design decision) carries no theme dependency; verdict/status colour is never the sole
channel per ``08-L_ui_standardization.md``, so a text-only badge is spec-conformant on
its own. The context menu is intentionally partial -- see the story's Notes section for
which ``description.md`` §3.3 items are wired this story and why.

The in-use-by-run marker is orthogonal to the validation/dirty badge -- ``description.md``
§9 EC-TE-07 says a file being read by an active run "carries an in-use banner", independent
of whether that same file is also dirty (a running benchmark already cached its tasks at
run-start, so editing the file while it is in-use is permitted). It is therefore rendered
as a second, always-appended glyph rather than folded into ``badge_text_for_row``'s
single-glyph precedence chain.
"""

from PySide6.QtCore import QPoint, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.ui.task_editor.models import FileRowViewModel, ValidationState

__all__: list[str] = ["FilesPaneWidget"]

_YAML_SUFFIXES = frozenset({".yaml", ".yml"})
_BADGE_RELOAD_PENDING = "[reload pending]"
_BADGE_ERROR = "[error]"
_BADGE_WARNING = "[warning]"
_BADGE_DIRTY = "[dirty]"
_BADGE_CLEAN = "[clean]"
_IN_USE_MARKER = "[in use]"
_IN_USE_TOOLTIP_SUFFIX = "\n\nIn use by a running benchmark."


def badge_text_for_row(row: FileRowViewModel) -> str:
    """Resolve one file row's displayed badge glyph (STORY-068-AC-2).

    Precedence: reload-pending > error/warning > dirty > clean.
    """
    if row.is_external_changed:
        return _BADGE_RELOAD_PENDING
    if row.validation_state is ValidationState.ERROR:
        return _BADGE_ERROR
    if row.validation_state is ValidationState.WARNING:
        return _BADGE_WARNING
    if row.is_dirty:
        return _BADGE_DIRTY
    return _BADGE_CLEAN


def row_label_for_row(row: FileRowViewModel) -> str:
    """Resolve one file row's full displayed label (STORY-068-AC-2, AC-4).

    The validation/dirty badge glyph is always shown first; the in-use-by-run
    marker, when present, is appended after the display name -- it is an
    orthogonal indicator, not a precedence competitor of the badge glyph
    (``description.md`` §9 EC-TE-07).
    """
    label = f"{badge_text_for_row(row)} {row.display_name}"
    if row.is_in_use_by_run:
        label = f"{label} {_IN_USE_MARKER}"
    return label


class FilesPaneWidget(QWidget):
    """Passive flat file-buffer list; forwards every user action via signals."""

    row_selected = Signal(int)
    files_dropped = Signal(object)
    close_requested = Signal(int)
    close_others_requested = Signal(int)
    reveal_requested = Signal(int)
    reload_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("task_editor.files_pane")
        self.setAcceptDrops(True)
        self._rows: tuple[FileRowViewModel, ...] = ()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._list = QListWidget()
        self._list.setObjectName("task_editor.files_pane.list")
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.currentRowChanged.connect(self._on_current_row_changed)
        self._list.setContextMenuPolicy(self._list.contextMenuPolicy().CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu_requested)
        layout.addWidget(self._list)

        footer = QHBoxLayout()
        self.open_file_button = QPushButton("Open File")
        self.open_file_button.setObjectName("task_editor.files_pane.open_file")
        footer.addWidget(self.open_file_button)

        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.setObjectName("task_editor.files_pane.open_folder")
        footer.addWidget(self.open_folder_button)

        self.new_file_button = QPushButton("New File")
        self.new_file_button.setObjectName("task_editor.files_pane.new_file")
        footer.addWidget(self.new_file_button)
        layout.addLayout(footer)

    def apply(self, rows: tuple[FileRowViewModel, ...]) -> None:
        """Push the current file-row list (§3.3)."""
        self._rows = rows
        self._list.blockSignals(True)  # noqa: FBT003  # Qt's own blockSignals(bool) API
        try:
            self._list.clear()
            for row in rows:
                item = QListWidgetItem(row_label_for_row(row))
                tooltip = row.path
                if row.is_in_use_by_run:
                    tooltip = f"{tooltip}{_IN_USE_TOOLTIP_SUFFIX}"
                item.setToolTip(tooltip)
                self._list.addItem(item)
            active_index = next((i for i, row in enumerate(rows) if row.is_active), None)
            if active_index is not None:
                self._list.setCurrentRow(active_index)
        finally:
            self._list.blockSignals(False)  # noqa: FBT003  # Qt's own blockSignals(bool) API

    def _on_current_row_changed(self, row: int) -> None:
        if row < 0:
            return
        self.row_selected.emit(row)

    def _on_context_menu_requested(self, position: QPoint) -> None:
        item = self._list.itemAt(position)
        if item is None:
            return  # type: ignore[unreachable]  # PySide6 stub gap: itemAt() is typed non-Optional but returns None off-item
        index = self._list.row(item)
        row = self._rows[index]
        menu = QMenu(self)
        close_action = menu.addAction("Close")
        close_action.setEnabled(not row.is_dirty)
        if row.is_dirty:
            close_action.setToolTip("Unsaved changes -- close-confirmation ships in a later story.")
        close_others_action = menu.addAction("Close Others")
        reveal_action = menu.addAction("Reveal in File Manager")
        reload_action = menu.addAction("Reload from Disk")
        reload_action.setEnabled(not row.is_dirty)
        if row.is_dirty:
            reload_action.setToolTip(
                "Unsaved changes -- reload-confirmation ships in a later story."
            )
        chosen = menu.exec(self._list.viewport().mapToGlobal(position))
        if chosen is close_action:
            self.close_requested.emit(index)
        elif chosen is close_others_action:
            self.close_others_requested.emit(index)
        elif chosen is reveal_action:
            self.reveal_requested.emit(index)
        elif chosen is reload_action:
            self.reload_requested.emit(index)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = tuple(url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile())
        if paths:
            self.files_dropped.emit(paths)
        event.acceptProposedAction()
