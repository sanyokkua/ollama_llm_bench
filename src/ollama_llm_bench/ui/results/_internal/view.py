"""``ResultView`` -- the passive Result widget shell: the run-selector dropdown, the
four-tab strip with empty tab-body host placeholders, and the uniform export footer
(STORY-061).

Passive View: renders a ``ResultViewModel`` via ``apply()`` and emits widget-local Qt
signals on user interaction; imports no adapter Gateway, no reactive store, and no
backend service symbol beyond ``backend.domain``/``backend.events`` DTOs it renders.
The four tab bodies themselves are empty mounting-point containers -- STORY-062..065
mount their own tab views into them; this story constructs no tab content.
"""

from functools import partial
from typing import Final

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.ui.results._internal.theme_lookup import resolve_spacing_tokens
from ollama_llm_bench.ui.results.models import FooterViewModel, ResultViewModel
from ollama_llm_bench.ui.theme import PlatformKind

__all__: list[str] = ["ResultView"]

_TAB_NAMES: Final[tuple[str, ...]] = ("summary", "details", "charts", "run_analysis")
_TAB_LABELS: Final[tuple[str, ...]] = ("Summary", "Details", "Charts", "Run Analysis")
_TAB_HOST_OBJECT_NAMES: Final[tuple[str, ...]] = (
    "summary_tab_host",
    "details_tab_host",
    "charts_tab_host",
    "run_analysis_tab_host",
)


class ResultView(QWidget):
    """Passive Result widget shell: header dropdown, tab strip, footer host."""

    dropdown_changed = Signal(int)
    tab_changed = Signal(str)
    export_clicked = Signal(str)
    save_directly_toggled = Signal(bool)
    open_exports_folder_clicked = Signal()

    def __init__(self, *, platform_kind: PlatformKind = PlatformKind.UNKNOWN) -> None:
        super().__init__()
        self.setObjectName("result_widget.view")
        self._platform_kind = platform_kind
        self._build_ui()

    def _build_ui(self) -> None:
        spacing = resolve_spacing_tokens(platform_kind=self._platform_kind).spacing
        root = QVBoxLayout(self)
        root.setContentsMargins(spacing.md, spacing.md, spacing.md, spacing.md)
        root.setSpacing(spacing.md)

        self._run_dropdown = QComboBox()
        self._run_dropdown.setObjectName("result_widget.run_dropdown")
        self._run_dropdown.currentIndexChanged.connect(self._on_dropdown_index_changed)
        root.addWidget(self._run_dropdown)

        self._tab_widget = QTabWidget()
        self._tab_widget.setObjectName("result_widget.tabs")
        self._tab_hosts: dict[str, QWidget] = {}
        for tab_name, label, object_name in zip(
            _TAB_NAMES, _TAB_LABELS, _TAB_HOST_OBJECT_NAMES, strict=True
        ):
            host = QWidget()
            host.setObjectName(object_name)
            self._tab_hosts[tab_name] = host
            self._tab_widget.addTab(host, label)
        self._tab_widget.currentChanged.connect(self._on_tab_index_changed)
        root.addWidget(self._tab_widget, 1)

        footer_row = QHBoxLayout()
        footer_row.setSpacing(spacing.sm)
        self._export_buttons_layout = QHBoxLayout()
        footer_row.addLayout(self._export_buttons_layout)
        footer_row.addStretch()
        self._save_directly_checkbox = QCheckBox("Save to app data folder")
        self._save_directly_checkbox.setObjectName("result_widget.save_directly")
        self._save_directly_checkbox.toggled.connect(self.save_directly_toggled)
        footer_row.addWidget(self._save_directly_checkbox)
        self._open_folder_button = QPushButton("Open Exports Folder")
        self._open_folder_button.setObjectName("result_widget.open_exports_folder")
        self._open_folder_button.setProperty("role", "outlined-muted-button")
        self._open_folder_button.clicked.connect(self.open_exports_folder_clicked)
        footer_row.addWidget(self._open_folder_button)
        root.addLayout(footer_row)

    def tab_host(self, tab_name: str) -> QWidget:
        """Return the empty mounting-point container for ``tab_name``.

        A later tab story (STORY-062..065) mounts its own tab view into the
        widget returned here.
        """
        return self._tab_hosts[tab_name]

    def apply(self, vm: ResultViewModel) -> None:
        """Render the header, tab strip, and footer from ``vm`` (idempotent)."""
        self._apply_dropdown(vm)
        self._apply_tabs(vm)
        self._apply_footer(vm.footer)

    def _apply_dropdown(self, vm: ResultViewModel) -> None:
        self._run_dropdown.blockSignals(True)  # noqa: FBT003  # Qt's own blockSignals(bool) API
        try:
            self._run_dropdown.clear()
            for run_id, name in vm.run_options:
                self._run_dropdown.addItem(name, userData=run_id)
            if vm.selected_run_id is not None:
                index = self._run_dropdown.findData(vm.selected_run_id)
                if index >= 0:
                    self._run_dropdown.setCurrentIndex(index)
            self._run_dropdown.setEnabled(bool(vm.run_options))
        finally:
            self._run_dropdown.blockSignals(False)  # noqa: FBT003  # Qt's own blockSignals(bool) API

    def _apply_tabs(self, vm: ResultViewModel) -> None:
        index = _TAB_NAMES.index(vm.active_tab) if vm.active_tab in _TAB_NAMES else 0
        self._tab_widget.blockSignals(True)  # noqa: FBT003  # Qt's own blockSignals(bool) API
        try:
            self._tab_widget.setCurrentIndex(index)
        finally:
            self._tab_widget.blockSignals(False)  # noqa: FBT003  # Qt's own blockSignals(bool) API
        self._tab_widget.setEnabled(vm.widget_state == "run_selected")

    def _apply_footer(self, footer_vm: FooterViewModel) -> None:
        while self._export_buttons_layout.count():
            item = self._export_buttons_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for label in footer_vm.export_buttons:
            button = QPushButton(label)
            slug = label.replace(" ", "_").lower()
            button.setObjectName(f"result_widget.export.{slug}")
            button.setEnabled(footer_vm.exports_enabled)
            button.setToolTip(footer_vm.disabled_tooltip or "")
            button.clicked.connect(partial(self.export_clicked.emit, label))
            self._export_buttons_layout.addWidget(button)

        self._save_directly_checkbox.blockSignals(True)  # noqa: FBT003  # Qt's blockSignals(bool)
        try:
            self._save_directly_checkbox.setChecked(footer_vm.save_directly)
        finally:
            self._save_directly_checkbox.blockSignals(False)  # noqa: FBT003  # Qt's blockSignals(bool)
        self._open_folder_button.setVisible(footer_vm.show_open_folder)

    def _on_dropdown_index_changed(self, index: int) -> None:
        if index < 0:
            return
        run_id = self._run_dropdown.itemData(index)
        if run_id is None:
            return
        self.dropdown_changed.emit(int(run_id))

    def _on_tab_index_changed(self, index: int) -> None:
        if index < 0:
            return
        self.tab_changed.emit(_TAB_NAMES[index])
