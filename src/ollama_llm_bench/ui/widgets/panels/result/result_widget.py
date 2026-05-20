"""Result panel widget — displays benchmark run summaries, detailed task results, charts, and judge analysis."""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from PySide6.QtCore import QSettings, QSortFilterProxyModel, QStandardPaths, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QSplitter,
    QTableView,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.models import (
    AvgSummaryTableItem,
    BenchmarkResult,
    BenchmarkRun,
    JudgeSummaryEvent,
    PerfAnalysisEvent,
    RunRenamedEvent,
    SummaryTableItem,
)
from ollama_llm_bench.backend.core.ui_controllers import ResultWidgetControllerApi
from ollama_llm_bench.backend.utils.filename_utils import sanitize_filename
from ollama_llm_bench.ui.models.detailed_table_model import DetailedTableModel
from ollama_llm_bench.ui.models.numeric_sort_proxy_model import NumericSortProxyModel
from ollama_llm_bench.ui.models.summary_table_model import SummaryTableModel
from ollama_llm_bench.ui.utils.widget_utils import set_benchmark_run_on_dropdown
from ollama_llm_bench.ui.widgets.panels.result.charts_widget import ChartsSwitcherWidget
from ollama_llm_bench.ui.widgets.panels.result.judge_analysis_widget import JudgeAnalysisWidget
from ollama_llm_bench.ui.widgets.panels.result.table_detach_dialog import TableDetachDialog
from ollama_llm_bench.ui.widgets.panels.result.task_detail_widget import TaskDetailWidget
from ollama_llm_bench.ui.widgets.panels.result.value_set_filter_dialog import ValueSetFilterDialog

logger = logging.getLogger(__name__)

_VERTICAL_SPACING: Final[int] = 10
_RUN_LABEL_TEXT: Final[str] = "Run Results:"
_SUMMARY_LABEL_TEXT: Final[str] = "Summary: Average Performance per Model"
_DETAILED_LABEL_TEXT: Final[str] = "Detailed Results"
_SETTINGS_SUMMARY_COLS: Final[str] = "ui/summary_table_visible_columns"
_SETTINGS_DETAILED_COLS: Final[str] = "ui/detailed_table_visible_columns"


class ResultWidget(QWidget):
    """UI component displaying benchmark results with summary, detailed, charts, and judge analysis tabs.

    Provides column show/hide, per-column filtering, filter-aware CSV/Markdown export,
    and detach-to-window functionality for both summary and detailed tables.
    """

    def __init__(self, controller: ResultWidgetControllerApi) -> None:
        """Initialise the result widget.

        Args:
            controller: Controller API for handling user interactions and data updates.
        """
        super().__init__()
        self._controller = controller
        self._latest_summary: list[AvgSummaryTableItem] = []
        self._latest_details: list[SummaryTableItem] = []
        self._judge_summaries: dict[int, str] = {}
        self._perf_analyses: dict[int, str] = {}
        self._active_run_id: int | None = None
        self._user_selected_run: bool = False
        self._benchmark_is_running: bool = False
        self._summary_detach_dialog: TableDetachDialog | None = None
        self._detailed_detach_dialog: TableDetachDialog | None = None

        # Source models
        self._summary_source_model = SummaryTableModel()
        self._summary_proxy = NumericSortProxyModel()
        self._summary_proxy.setSourceModel(self._summary_source_model)

        self._detailed_source_model = DetailedTableModel()
        self._detailed_proxy = NumericSortProxyModel()
        self._detailed_proxy.setSourceModel(self._detailed_source_model)

        # Controls
        self._run_label = QLabel(_RUN_LABEL_TEXT)
        self._run_dropdown = QComboBox()
        self._run_dropdown.setToolTip("Select a previous benchmark run to display its results.")
        self._delete_button = QPushButton("Delete")
        self._delete_button.setToolTip(
            "Permanently delete the selected benchmark run and all its stored results from the database."
        )
        self._rename_run_btn = QToolButton()
        self._rename_run_btn.setText("✏")
        self._rename_run_btn.setToolTip("Rename this run")
        self._rename_run_btn.setProperty("role", "icon-btn")
        self._rename_run_btn.setEnabled(False)
        self._summary_label = QLabel(_SUMMARY_LABEL_TEXT)
        self._detailed_label = QLabel(_DETAILED_LABEL_TEXT)
        self._summary_csv_button = QPushButton("Export as CSV")
        self._summary_csv_button.setToolTip(
            "Export the summary results table to a CSV file. Saves to the configured export directory."
        )
        self._summary_md_button = QPushButton("Export as Markdown")
        self._summary_md_button.setToolTip(
            "Export the summary results table to a Markdown file. Saves to the configured export directory."
        )
        self._detailed_csv_button = QPushButton("Export as CSV")
        self._detailed_csv_button.setToolTip(
            "Export the detailed per-task results table to a CSV file. Saves to the configured export directory."
        )
        self._detailed_md_button = QPushButton("Export as Markdown")
        self._detailed_md_button.setToolTip(
            "Export the detailed per-task results table to a Markdown file. Saves to the configured export directory."
        )
        self._summary_detach_button = QPushButton("Detach window")
        self._summary_detach_button.setToolTip(
            "Open the summary results table in a separate floating window for side-by-side comparison."
        )
        self._detailed_detach_button = QPushButton("Detach window")
        self._detailed_detach_button.setToolTip(
            "Open the detailed per-task results table in a separate floating window for side-by-side comparison."
        )
        self._summary_clear_filters_button = QPushButton("Clear filters")
        self._summary_clear_filters_button.setToolTip(
            "Clear all active column filters on the summary table, restoring the full result set."
        )
        self._detailed_clear_filters_button = QPushButton("Clear filters")
        self._detailed_clear_filters_button.setToolTip(
            "Clear all active column filters on the detailed table, restoring the full result set."
        )
        self._tab_widget = QTabWidget()
        self._charts_widget = ChartsSwitcherWidget(app_settings=controller.get_app_settings_service())
        self._judge_analysis_widget = JudgeAnalysisWidget()
        self._task_detail_widget = TaskDetailWidget()
        self._summary_also_save_checkbox = QCheckBox("Save directly to app data folder (no dialog)")
        self._summary_also_save_checkbox.setToolTip(
            "When checked, also saves the summary export to the configured log folder"
            " alongside the primary export location."
        )
        self._details_also_save_checkbox = QCheckBox("Save directly to app data folder (no dialog)")
        self._details_also_save_checkbox.setToolTip(
            "When checked, also saves the detailed export to the configured log folder"
            " alongside the primary export location."
        )

        for btn in (
            self._delete_button,
            self._summary_csv_button,
            self._summary_md_button,
            self._detailed_csv_button,
            self._detailed_md_button,
            self._summary_detach_button,
            self._detailed_detach_button,
            self._summary_clear_filters_button,
            self._detailed_clear_filters_button,
        ):
            btn.setProperty("role", "secondary")

        self._benchmark_sensitive_widgets: list[QWidget] = [
            self._run_label,
            self._delete_button,
            self._summary_label,
            self._detailed_label,
            self._summary_csv_button,
            self._summary_md_button,
            self._detailed_csv_button,
            self._detailed_md_button,
            self._summary_also_save_checkbox,
            self._details_also_save_checkbox,
        ]

        # Table views
        self._summary_view = self._create_table_view(self._summary_proxy)
        self._detailed_view = self._create_table_view(self._detailed_proxy)

        self._setup_ui_layout()
        self._setup_header_menus()
        self._restore_column_visibility()
        self._connect_signals()
        self._subscribe_to_controller_events()

        logger.debug("ResultWidget initialized")

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _create_table_view(proxy: QSortFilterProxyModel) -> QTableView:
        """Create and configure a QTableView backed by the given proxy model.

        Args:
            proxy: The sort/filter proxy model to attach.

        Returns:
            Configured QTableView instance.
        """
        view = QTableView()
        view.setModel(proxy)
        view.setSortingEnabled(True)
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = view.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        view.verticalHeader().setVisible(False)
        return view

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _setup_ui_layout(self) -> None:
        """Construct the widget's layout hierarchy."""
        # Top controls
        top_layout = QHBoxLayout()
        top_layout.addWidget(self._run_label)
        top_layout.addWidget(self._run_dropdown)
        top_layout.addWidget(self._rename_run_btn)
        top_layout.addWidget(self._delete_button)
        top_layout.addStretch()

        # Summary tab
        summary_tab = QWidget()
        summary_toolbar = QHBoxLayout()
        summary_toolbar.addWidget(self._summary_clear_filters_button)
        summary_toolbar.addWidget(self._summary_detach_button)
        summary_toolbar.addStretch()
        summary_export_row = QHBoxLayout()
        summary_export_row.addWidget(self._summary_csv_button)
        summary_export_row.addWidget(self._summary_md_button)
        summary_layout = QVBoxLayout(summary_tab)
        summary_layout.addWidget(self._summary_label)
        summary_layout.addLayout(summary_toolbar)
        summary_layout.addWidget(self._summary_view, 1)
        summary_layout.addLayout(summary_export_row)
        summary_layout.addWidget(self._summary_also_save_checkbox)

        # Details tab
        details_tab = QWidget()
        detailed_toolbar = QHBoxLayout()
        detailed_toolbar.addWidget(self._detailed_clear_filters_button)
        detailed_toolbar.addWidget(self._detailed_detach_button)
        detailed_toolbar.addStretch()
        details_splitter = QSplitter(Qt.Orientation.Vertical)
        details_splitter.addWidget(self._detailed_view)
        details_splitter.addWidget(self._task_detail_widget)
        details_splitter.setSizes([400, 200])
        detailed_export_row = QHBoxLayout()
        detailed_export_row.addWidget(self._detailed_csv_button)
        detailed_export_row.addWidget(self._detailed_md_button)
        details_layout = QVBoxLayout(details_tab)
        details_layout.addWidget(self._detailed_label)
        details_layout.addLayout(detailed_toolbar)
        details_layout.addWidget(details_splitter, 1)
        details_layout.addLayout(detailed_export_row)
        details_layout.addWidget(self._details_also_save_checkbox)

        # Tabs
        self._tab_widget.addTab(summary_tab, "Summary")
        self._tab_widget.addTab(details_tab, "Details")
        self._tab_widget.addTab(self._charts_widget, "Charts")
        self._tab_widget.addTab(self._judge_analysis_widget, "Judge Analysis")

        # Root layout
        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addSpacing(_VERTICAL_SPACING)
        main_layout.addWidget(self._tab_widget)
        self.setLayout(main_layout)

    # ------------------------------------------------------------------
    # Header context menus
    # ------------------------------------------------------------------

    def _setup_header_menus(self) -> None:
        """Wire right-click context menus on both table headers."""
        for view, key in (
            (self._summary_view, _SETTINGS_SUMMARY_COLS),
            (self._detailed_view, _SETTINGS_DETAILED_COLS),
        ):
            header = view.horizontalHeader()
            header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            header.customContextMenuRequested.connect(
                lambda pos, v=view, k=key: self._show_header_context_menu(pos, v, k)
            )

    def _show_header_context_menu(self, pos: Any, view: QTableView, settings_key: str) -> None:
        """Display a context menu on the table header for column show/hide and filtering.

        Args:
            pos: Cursor position (relative to the header viewport).
            view: The QTableView whose header was right-clicked.
            settings_key: QSettings key for persisting column visibility.
        """
        proxy = view.model()
        if proxy is None:
            return
        col_count = proxy.columnCount()

        # Count currently visible columns to enforce last-visible constraint
        visible_count = sum(1 for c in range(col_count) if not view.isColumnHidden(c))

        menu = QMenu(view)

        # Section label
        section_action = QAction("Columns", menu)
        section_action.setEnabled(False)
        menu.addAction(section_action)
        menu.addSeparator()

        # Per-column toggle actions
        col_actions: list[QAction] = []
        for col in range(col_count):
            name = proxy.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) or f"Col {col}"
            action = QAction(str(name), menu)
            action.setCheckable(True)
            is_visible = not view.isColumnHidden(col)
            action.setChecked(is_visible)
            if is_visible and visible_count == 1:
                action.setEnabled(False)
                action.setToolTip("At least one column must remain visible.")
            action.triggered.connect(
                lambda checked, c=col, v=view, sk=settings_key, a=action: self._on_column_visibility_toggled(
                    checked, c, v, sk, a
                )
            )
            menu.addAction(action)
            col_actions.append(action)

        menu.addSeparator()

        show_all_action = QAction("Show all", menu)
        show_all_action.triggered.connect(lambda: self._show_all_columns(view, settings_key))
        menu.addAction(show_all_action)

        reset_action = QAction("Reset to default", menu)
        reset_action.triggered.connect(lambda: self._show_all_columns(view, settings_key))
        menu.addAction(reset_action)

        menu.addSeparator()

        # Per-column filter actions
        numeric_proxy = view.model()
        for col in range(col_count):
            col_name = proxy.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) or f"Col {col}"
            filter_action = QAction(f"Filter by values: {col_name}…", menu)
            if isinstance(numeric_proxy, NumericSortProxyModel):
                np_ref = numeric_proxy
                filter_action.triggered.connect(
                    lambda _checked=False, c=col, np=np_ref, v=view: self._open_column_filter(c, np, v)
                )
            menu.addAction(filter_action)

        menu.exec(view.horizontalHeader().viewport().mapToGlobal(pos))

    def _on_column_visibility_toggled(
        self,
        checked: bool,
        col: int,
        view: QTableView,
        settings_key: str,
        action: QAction,
    ) -> None:
        """Toggle a column's visibility and persist the change.

        Args:
            checked: Whether the action was checked (column should be visible).
            col: Column index to toggle.
            view: The QTableView that owns the column.
            settings_key: QSettings key for persisting visibility state.
            action: The triggering QAction (used to restore check state on constraint violation).
        """
        if not checked:
            proxy = view.model()
            col_count = proxy.columnCount() if proxy is not None else 0
            visible_count = sum(1 for c in range(col_count) if not view.isColumnHidden(c))
            if visible_count <= 1:
                action.setChecked(True)
                return
            # If the hidden column was the active sort column, clear the sort indicator
            sort_col = view.horizontalHeader().sortIndicatorSection()
            if sort_col == col:
                view.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)

        view.setColumnHidden(col, not checked)
        self._save_column_visibility(view, settings_key)
        view.horizontalHeader().viewport().update()

    def _show_all_columns(self, view: QTableView, settings_key: str) -> None:
        """Show all columns and persist the visibility state.

        Args:
            view: The QTableView whose columns should be revealed.
            settings_key: QSettings key for persisting visibility state.
        """
        proxy = view.model()
        if proxy is None:
            return
        for col in range(proxy.columnCount()):
            view.setColumnHidden(col, False)
        self._save_column_visibility(view, settings_key)
        view.horizontalHeader().viewport().update()

    def _open_column_filter(self, col: int, proxy: NumericSortProxyModel, view: QTableView) -> None:
        """Open the ValueSetFilterDialog for the given column.

        Args:
            col: Column index to filter.
            proxy: Proxy model that holds filter state.
            view: The QTableView whose header viewport must be refreshed after filtering.
        """
        dlg = ValueSetFilterDialog(col, proxy, self)
        dlg.exec()
        view.horizontalHeader().viewport().update()

    def _save_column_visibility(self, view: QTableView, settings_key: str) -> None:
        """Persist the current column visibility state to QSettings.

        Args:
            view: The QTableView whose visibility state should be saved.
            settings_key: QSettings key to store under.
        """
        proxy = view.model()
        col_count = proxy.columnCount() if proxy is not None else 0
        visibility = [not view.isColumnHidden(i) for i in range(col_count)]
        QSettings().setValue(settings_key, visibility)

    def _restore_column_visibility(self) -> None:
        """Restore column visibility from QSettings for both table views."""
        settings = QSettings()
        self._apply_saved_visibility(self._summary_view, settings.value(_SETTINGS_SUMMARY_COLS))
        self._apply_saved_visibility(self._detailed_view, settings.value(_SETTINGS_DETAILED_COLS))

    @staticmethod
    def _apply_saved_visibility(view: QTableView, saved: object) -> None:
        """Apply a saved visibility list to a table view.

        Args:
            view: The QTableView to configure.
            saved: Saved value from QSettings (expected to be a list of bools).
        """
        if not isinstance(saved, list):
            return
        proxy = view.model()
        col_count = proxy.columnCount() if proxy is not None else 0
        if len(saved) != col_count:
            return
        for col, visible in enumerate(saved):
            is_visible = visible if isinstance(visible, bool) else str(visible).lower() == "true"
            view.setColumnHidden(col, not is_visible)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """Connect UI widget signals to handler methods."""
        self._run_dropdown.currentIndexChanged.connect(self._on_run_dropdown_changed)
        self._run_dropdown.activated.connect(self._on_run_dropdown_activated)
        self._rename_run_btn.clicked.connect(self._on_rename_run_clicked)
        self._delete_button.clicked.connect(self._controller.handle_delete_click)
        self._summary_csv_button.clicked.connect(self._on_summary_export_csv)
        self._summary_md_button.clicked.connect(self._on_summary_export_md)
        self._detailed_csv_button.clicked.connect(self._on_details_export_csv)
        self._detailed_md_button.clicked.connect(self._on_details_export_md)
        self._summary_clear_filters_button.clicked.connect(self._on_summary_clear_filters)
        self._detailed_clear_filters_button.clicked.connect(self._on_detailed_clear_filters)
        self._summary_detach_button.clicked.connect(self._on_summary_detach)
        self._detailed_detach_button.clicked.connect(self._on_detailed_detach)
        self._summary_also_save_checkbox.toggled.connect(self._controller.set_also_save_to_default)
        self._details_also_save_checkbox.toggled.connect(self._controller.set_also_save_to_default)
        self._detailed_view.selectionModel().selectionChanged.connect(self._on_task_row_selected)

    def _subscribe_to_controller_events(self) -> None:
        """Subscribe to controller state updates and initialise checkbox state."""
        self._controller.subscribe_to_runs_change(self._on_runs_changed, parent=self)
        self._controller.subscribe_to_run_id_changed(self._on_run_id_changed, parent=self)
        self._controller.subscribe_to_summary_data_change(self._on_summary_data_changed, parent=self)
        self._controller.subscribe_to_detailed_data_change(self._on_detailed_data_changed, parent=self)
        self._controller.subscribe_to_benchmark_status_change(self._on_benchmark_is_running_changed, parent=self)
        self._controller.subscribe_to_judge_summary(self._on_judge_summary_received, parent=self)
        self._controller.subscribe_to_perf_analysis(self._on_perf_analysis_received, parent=self)
        self._controller.subscribe_to_chart_data_change(self._on_chart_data_changed, parent=self)
        self._controller.subscribe_to_run_renamed(self._on_run_renamed, parent=self)
        initial = self._controller.get_also_save_to_default()
        self._summary_also_save_checkbox.setChecked(initial)
        self._details_also_save_checkbox.setChecked(initial)

    # ------------------------------------------------------------------
    # Event handlers — controller subscriptions
    # ------------------------------------------------------------------

    def _on_run_dropdown_changed(self) -> None:
        """Handle user selection of a different benchmark run from the dropdown."""
        run_id = self._run_dropdown.currentData()
        self._rename_run_btn.setEnabled(run_id is not None)
        if run_id is not None:
            self._summary_proxy.clear_all_filters()
            self._detailed_proxy.clear_all_filters()
            self._controller.handle_run_selection_change(run_id)
            logger.debug("Run ID selected: %s", run_id)

    def _on_run_dropdown_activated(self) -> None:
        """Mark that the user has explicitly chosen a run from the dropdown."""
        if self._run_dropdown.currentData() is not None:
            self._user_selected_run = True

    def _on_runs_changed(self, run_ids: list[tuple[int, str]]) -> None:
        """Update the run dropdown with available benchmark runs.

        Args:
            run_ids: List of (run_id, run_name) tuples.
        """
        logger.debug("Updating runs list: %d entries", len(run_ids))
        # Preserve the user's manual selection across dropdown rebuilds.
        preserved_id = self._run_dropdown.currentData() if self._user_selected_run else None
        self._run_dropdown.clear()
        for run_id, name in run_ids:
            self._run_dropdown.addItem(name, run_id)
        restore_id = preserved_id if preserved_id is not None else self._active_run_id
        if restore_id is not None:
            set_benchmark_run_on_dropdown(restore_id, self._run_dropdown, logger)

    def _on_rename_run_clicked(self) -> None:
        """Open the rename dialog for the currently selected run."""
        from ollama_llm_bench.ui.widgets.panels.rename_run_dialog import RenameRunDialog

        run_id: int | None = self._run_dropdown.currentData()
        if run_id is None:
            return
        existing = self._controller.get_run_names(exclude_run_id=run_id)
        current_name = self._run_dropdown.currentText()
        dlg = RenameRunDialog(current_name=current_name, existing_names=existing, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._controller.rename_run(run_id=run_id, new_name=dlg.new_name)

    def _on_run_renamed(self, event: RunRenamedEvent) -> None:
        """Update the dropdown item text when a run is renamed.

        Args:
            event: The rename event carrying run_id and new_name.
        """
        for i in range(self._run_dropdown.count()):
            if self._run_dropdown.itemData(i) == event.run_id:
                self._run_dropdown.setItemText(i, event.new_name)
                break

    def _on_run_id_changed(self, run_id: int | None) -> None:
        """Sync the dropdown selection with the currently active run ID.

        Args:
            run_id: Identifier of the active run, or None when no run is selected.
        """
        self._active_run_id = run_id
        if run_id is None:
            return
        # While a benchmark is running, don't override the user's explicit run selection.
        if self._benchmark_is_running and self._user_selected_run and run_id != self._run_dropdown.currentData():
            return
        set_benchmark_run_on_dropdown(run_id, self._run_dropdown, logger)
        if run_id in self._judge_summaries:
            self._judge_analysis_widget.show_summary(self._judge_summaries[run_id])
        elif run_id in self._perf_analyses:
            self._judge_analysis_widget.show_perf_analysis(self._perf_analyses[run_id])
        else:
            # Cache is cold (e.g. after app restart) — fall back to DB read.
            run = self._controller.get_run(run_id)
            if run is not None and run.judge_summary:
                self._judge_summaries[run_id] = run.judge_summary
                self._judge_analysis_widget.show_summary(run.judge_summary)
            elif run is not None and run.perf_analysis_result:
                self._perf_analyses[run_id] = run.perf_analysis_result
                self._judge_analysis_widget.show_perf_analysis(run.perf_analysis_result)
            else:
                self._judge_analysis_widget.clear()

    def _on_summary_data_changed(self, data: list[AvgSummaryTableItem]) -> None:
        """Update the summary table model and refresh charts.

        Args:
            data: List of averaged summary items to display.
        """
        logger.debug("Updating summary table with %d models", len(data))
        self._latest_summary = data
        self._summary_source_model.update_data(data)

    def _on_detailed_data_changed(self, data: list[SummaryTableItem]) -> None:
        """Update the detailed table model, refresh charts, and clear task detail.

        Args:
            data: List of per-task detailed items to display.
        """
        logger.debug("Updating detailed table with %d tasks", len(data))
        self._latest_details = data
        self._detailed_source_model.update_data(data)
        self._task_detail_widget.clear()

    def _on_benchmark_is_running_changed(self, is_running: bool) -> None:
        """Toggle UI interactivity based on benchmark execution status.

        Args:
            is_running: Current execution state of the benchmark.
        """
        logger.debug("Benchmark state changed: %s", "running" if is_running else "stopped")
        self._benchmark_is_running = is_running
        enabled = not is_running
        for widget in self._benchmark_sensitive_widgets:
            widget.setEnabled(enabled)
        if is_running:
            self._user_selected_run = False
            self._judge_analysis_widget.show_pending()

    def _on_judge_summary_received(self, event: JudgeSummaryEvent) -> None:
        """Cache judge summary and display it if the matching run is selected.

        Args:
            event: Judge summary event carrying run_id and summary_text.
        """
        self._judge_summaries[event.run_id] = event.summary_text
        current_run: int | None = self._run_dropdown.currentData()
        if current_run == event.run_id:
            self._judge_analysis_widget.show_summary(event.summary_text)

    def _on_perf_analysis_received(self, event: PerfAnalysisEvent) -> None:
        """Cache performance analysis and display it if the matching run is selected.

        Args:
            event: Performance analysis event carrying run_id and analysis_text.
        """
        self._perf_analyses[event.run_id] = event.analysis_text
        current_run: int | None = self._run_dropdown.currentData()
        if current_run == event.run_id:
            self._judge_analysis_widget.show_perf_analysis(event.analysis_text)

    def _on_chart_data_changed(self, run: BenchmarkRun | None, results: list[BenchmarkResult]) -> None:
        """Forward chart data to the charts widget when the controller emits an update.

        Args:
            run: Current BenchmarkRun, or None if none selected.
            results: All BenchmarkResult rows for the current run.
        """
        self._charts_widget.update_run_data(run=run, results=results)

    def _on_task_row_selected(self) -> None:
        """Handle row selection in the detailed table and update the task detail view."""
        indexes = self._detailed_view.selectionModel().selectedRows()
        if not indexes:
            self._task_detail_widget.clear()
            return
        proxy_row = indexes[0].row()
        source_index = self._detailed_proxy.mapToSource(self._detailed_proxy.index(proxy_row, 0))
        source_row = source_index.row()
        items = self._detailed_source_model._items  # same-package access for efficiency
        if source_row < 0 or source_row >= len(items):
            self._task_detail_widget.clear()
            return
        item = items[source_row]
        result = self._controller.handle_task_selected(item.model_name, item.task_id, item.prompt_version)
        if result is not None:
            self._task_detail_widget.show_result(result)
        else:
            self._task_detail_widget.clear()

    # ------------------------------------------------------------------
    # Filter clear handlers
    # ------------------------------------------------------------------

    def _on_summary_clear_filters(self) -> None:
        """Clear all active filters on the summary proxy model."""
        self._summary_proxy.clear_all_filters()
        self._summary_view.horizontalHeader().viewport().update()

    def _on_detailed_clear_filters(self) -> None:
        """Clear all active filters on the detailed proxy model."""
        self._detailed_proxy.clear_all_filters()
        self._detailed_view.horizontalHeader().viewport().update()

    # ------------------------------------------------------------------
    # Detach window handlers
    # ------------------------------------------------------------------

    def _on_summary_detach(self) -> None:
        """Open or raise the detached summary table window."""
        if self._summary_detach_dialog is not None:
            self._summary_detach_dialog.raise_()
            return
        run_name = self._run_dropdown.currentText() or "Run"
        dlg = TableDetachDialog(
            proxy_model=self._summary_proxy,
            run_name=run_name,
            table_name="Summary",
            parent=None,
        )
        dlg.closed.connect(self._on_summary_detach_closed)
        self._summary_detach_dialog = dlg
        self._summary_detach_button.setText("Attach")
        dlg.show()

    def _on_summary_detach_closed(self) -> None:
        """Reset the summary detach state when the detached window is closed."""
        self._summary_detach_dialog = None
        self._summary_detach_button.setText("Detach window")

    def _on_detailed_detach(self) -> None:
        """Open or raise the detached detailed table window."""
        if self._detailed_detach_dialog is not None:
            self._detailed_detach_dialog.raise_()
            return
        run_name = self._run_dropdown.currentText() or "Run"
        dlg = TableDetachDialog(
            proxy_model=self._detailed_proxy,
            run_name=run_name,
            table_name="Details",
            parent=None,
        )
        dlg.closed.connect(self._on_detailed_detach_closed)
        self._detailed_detach_dialog = dlg
        self._detailed_detach_button.setText("Attach")
        dlg.show()

    def _on_detailed_detach_closed(self) -> None:
        """Reset the detailed detach state when the detached window is closed."""
        self._detailed_detach_dialog = None
        self._detailed_detach_button.setText("Detach window")

    # ------------------------------------------------------------------
    # Export — filter-aware proxy export
    # ------------------------------------------------------------------

    def _export_from_proxy(
        self,
        proxy: NumericSortProxyModel,
        view: QTableView,
        path: Path,
        *,
        use_raw_for_csv: bool,
        as_csv: bool,
    ) -> int:
        """Export visible/filtered rows from the proxy model to a file.

        Args:
            proxy: The proxy model to read rows from (respects active filters and sort).
            view: The QTableView used to determine which columns are visible.
            path: Destination file path.
            use_raw_for_csv: When True and exporting as CSV, use UserRole raw values.
            as_csv: True to write CSV, False to write Markdown table.

        Returns:
            Number of rows written.
        """
        source_model = proxy.sourceModel()
        col_count = proxy.columnCount()
        visible_cols = [c for c in range(col_count) if not view.isColumnHidden(c)]

        headers: list[str] = []
        for c in visible_cols:
            h = source_model.headerData(c, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            headers.append(str(h) if h is not None else "")

        rows: list[list[Any]] = []
        for r in range(proxy.rowCount()):
            row_data: list[Any] = []
            for c in visible_cols:
                idx = proxy.index(r, c)
                if use_raw_for_csv and as_csv:
                    raw = idx.data(Qt.ItemDataRole.UserRole)
                    val = raw if raw is not None else idx.data(Qt.ItemDataRole.DisplayRole)
                else:
                    val = idx.data(Qt.ItemDataRole.DisplayRole)
                row_data.append(val if val is not None else "")
            rows.append(row_data)

        if as_csv:
            with path.open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
        else:
            lines: list[str] = []
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join("---" for _ in headers) + " |")
            for row_data in rows:
                lines.append("| " + " | ".join(str(v) for v in row_data) + " |")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        return len(rows)

    def _on_summary_export_csv(self) -> None:
        """Export the summary table as CSV — directly to app folder if checkbox is set."""
        if self._summary_also_save_checkbox.isChecked():
            self._controller.handle_summary_export_csv_click(None)
        else:
            path = self._get_save_path("Summary", "csv", "CSV Files (*.csv)")
            if path:
                n = self._export_from_proxy(
                    self._summary_proxy, self._summary_view, path, use_raw_for_csv=True, as_csv=True
                )
                logger.info("Exported %d rows to %s", n, path.name)

    def _on_summary_export_md(self) -> None:
        """Export the summary table as Markdown — directly to app folder if checkbox is set."""
        if self._summary_also_save_checkbox.isChecked():
            self._controller.handle_summary_export_md_click(None)
        else:
            path = self._get_save_path("Summary", "md", "Markdown Files (*.md)")
            if path:
                n = self._export_from_proxy(
                    self._summary_proxy, self._summary_view, path, use_raw_for_csv=False, as_csv=False
                )
                logger.info("Exported %d rows to %s", n, path.name)

    def _on_details_export_csv(self) -> None:
        """Export the detailed table as CSV — directly to app folder if checkbox is set."""
        if self._details_also_save_checkbox.isChecked():
            self._controller.handle_detailed_export_csv_click(None)
        else:
            path = self._get_save_path("Details", "csv", "CSV Files (*.csv)")
            if path:
                n = self._export_from_proxy(
                    self._detailed_proxy, self._detailed_view, path, use_raw_for_csv=True, as_csv=True
                )
                logger.info("Exported %d rows to %s", n, path.name)

    def _on_details_export_md(self) -> None:
        """Export the detailed table as Markdown — directly to app folder if checkbox is set."""
        if self._details_also_save_checkbox.isChecked():
            self._controller.handle_detailed_export_md_click(None)
        else:
            path = self._get_save_path("Details", "md", "Markdown Files (*.md)")
            if path:
                n = self._export_from_proxy(
                    self._detailed_proxy, self._detailed_view, path, use_raw_for_csv=False, as_csv=False
                )
                logger.info("Exported %d rows to %s", n, path.name)

    def _get_save_path(self, report_type: str, ext: str, file_filter: str) -> Path | None:
        """Prompt the user for a save location with a sensible default filename.

        Args:
            report_type: Human-readable report label (e.g. "Summary", "Details").
            ext: File extension without leading dot (e.g. "csv", "md").
            file_filter: Qt file filter string (e.g. "CSV Files (*.csv)").

        Returns:
            Resolved Path chosen by the user, or None if the dialog was cancelled.
        """
        run_name = self._run_dropdown.currentText() or "run"
        safe_name = sanitize_filename(run_name)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
        default_name = f"{safe_name}_{ts}_{report_type}.{ext}"
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        chosen_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Save {report_type} as {ext.upper()}",
            f"{desktop}/{default_name}",
            file_filter,
        )
        return Path(chosen_path) if chosen_path else None
