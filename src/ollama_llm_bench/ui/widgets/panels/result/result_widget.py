import logging
from typing import Callable, Final, List

from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.core.models import AvgSummaryTableItem, SummaryTableItem
from ollama_llm_bench.core.ui_controllers import ResultWidgetControllerApi
from ollama_llm_bench.utils.widget_utils import set_benchmark_run_on_dropdown

logger = logging.getLogger(__name__)

# Constants for UI configuration
_VERTICAL_SPACING: Final[int] = 10
_RUN_LABEL_TEXT: Final[str] = "Run Results:"
_SUMMARY_LABEL_TEXT: Final[str] = "Summary: Average Performance per Model"
_DETAILED_LABEL_TEXT: Final[str] = "Detailed Results for Run #5"


# Dataclasses for structured table configuration
class TableConfig:
    def __init__(
        self,
        header_labels: List[str],
        column_count: int,
        resize_mode: QHeaderView.ResizeMode = QHeaderView.ResizeMode.Interactive,
    ):
        self.header_labels = header_labels
        self.column_count = column_count
        self.resize_mode = resize_mode


SUMMARY_TABLE_CONFIG = TableConfig(
    header_labels=["MODEL", "AVG. TIME (s)", "AVG. TOKENS/s", "AVG. SCORE (%)"],
    column_count=4,
)

DETAILED_TABLE_CONFIG = TableConfig(
    header_labels=["MODEL", "TASK", "STATUS", "TIME (ms)", "Tokens", "TOKENS/s", "SCORE", "REASON"],
    column_count=8,
)


class ResultWidget(QWidget):
    """
    UI component for displaying benchmark results with summary and detailed views.
    Provides export functionality and run selection controls.
    """

    def __init__(self, controller: ResultWidgetControllerApi):
        """
        Initialize the result widget.

        Args:
            controller: Controller API for handling user interactions and data updates.
        """
        super().__init__()
        self._controller: ResultWidgetControllerApi = controller
        self._benchmark_sensitive_widgets: list[QWidget] = []  # Will populate during init

        # Initialize UI components with type hints
        self._run_label: QLabel = QLabel(_RUN_LABEL_TEXT)
        self._run_dropdown: QComboBox = QComboBox()
        self._delete_button: QPushButton = QPushButton("Delete")
        self._summary_label: QLabel = QLabel(_SUMMARY_LABEL_TEXT)
        self._detailed_label: QLabel = QLabel(_DETAILED_LABEL_TEXT)
        self._summary_csv_button: QPushButton = QPushButton("Export as CSV")
        self._summary_md_button: QPushButton = QPushButton("Export as Markdown")
        self._detailed_csv_button: QPushButton = QPushButton("Export as CSV")
        self._detailed_md_button: QPushButton = QPushButton("Export as Markdown")
        self._summary_table: QTableWidget = self._create_result_table(SUMMARY_TABLE_CONFIG)
        self._detailed_table: QTableWidget = self._create_result_table(DETAILED_TABLE_CONFIG)

        # Build UI layout
        self._setup_ui_layout()

        # Configure tables
        self._configure_tables()

        # Connect signals
        self._connect_signals()

        # Subscribe to controller events
        self._subscribe_to_controller_events()

        logger.debug("ResultWidget initialized")

    @staticmethod
    def _create_result_table(config: TableConfig) -> QTableWidget:
        """
        Factory method for creating configured result tables.

        Args:
            config: Table configuration specifying headers, column count, and resize behavior.

        Returns:
            Configured QTableWidget instance.
        """
        table = QTableWidget(0, config.column_count)
        table.setHorizontalHeaderLabels(config.header_labels)
        table.horizontalHeader().setSectionResizeMode(config.resize_mode)
        table.setSortingEnabled(True)
        return table

    def _setup_ui_layout(self) -> None:
        """
        Constructs the widget's layout hierarchy with proper spacing and organization.
        Creates sections for run selection, summary results, and detailed results.
        """
        # Top controls layout
        top_layout = QHBoxLayout()
        top_layout.addWidget(self._run_label)
        top_layout.addWidget(self._run_dropdown)
        top_layout.addWidget(self._delete_button)
        top_layout.addStretch()

        # Summary section
        summary_scroll = self._create_scrollable_table(self._summary_table)
        summary_export_layout = self._create_export_buttons_layout(
            self._summary_csv_button, self._summary_md_button,
        )
        summary_layout = QVBoxLayout()
        summary_layout.addWidget(self._summary_label)
        summary_layout.addWidget(summary_scroll)
        summary_layout.addLayout(summary_export_layout)

        # Detailed section
        detailed_scroll = self._create_scrollable_table(self._detailed_table)
        detailed_export_layout = self._create_export_buttons_layout(
            self._detailed_csv_button, self._detailed_md_button,
        )
        detailed_layout = QVBoxLayout()
        detailed_layout.addWidget(self._detailed_label)
        detailed_layout.addWidget(detailed_scroll)
        detailed_layout.addLayout(detailed_export_layout)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addSpacing(_VERTICAL_SPACING)
        main_layout.addLayout(summary_layout)
        main_layout.addSpacing(_VERTICAL_SPACING)
        main_layout.addLayout(detailed_layout)
        self.setLayout(main_layout)

        # Track widgets affected by benchmark state
        self._benchmark_sensitive_widgets = [
            self._run_label,
            self._run_dropdown,
            self._delete_button,
            self._summary_label,
            self._detailed_label,
            self._summary_csv_button,
            self._summary_md_button,
            self._detailed_csv_button,
            self._detailed_md_button,
            self._summary_table,
            self._detailed_table,
        ]

    @staticmethod
    def _create_scrollable_table(table: QTableWidget) -> QScrollArea:
        """
        Creates a scrollable container for a table widget.

        Args:
            table: Table to wrap in a scrollable area.

        Returns:
            QScrollArea containing the table.
        """
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(table)
        return scroll

    @staticmethod
    def _create_export_buttons_layout(
        csv_button: QPushButton, md_button: QPushButton,
    ) -> QHBoxLayout:
        """
        Creates a layout for export buttons.

        Args:
            csv_button: Button for CSV export.
            md_button: Button for Markdown export.

        Returns:
            QHBoxLayout containing both buttons.
        """
        layout = QHBoxLayout()
        layout.addWidget(csv_button)
        layout.addWidget(md_button)
        return layout

    def _configure_tables(self) -> None:
        """
        Applies consistent configuration to result tables.
        Configuration is handled during table creation.
        """
        # Configuration happens in _create_result_table
        pass

    def _connect_signals(self) -> None:
        """
        Connects UI events to controller handlers.
        """
        self._run_dropdown.currentIndexChanged.connect(self._on_run_dropdown_changed)
        self._delete_button.clicked.connect(self._controller.handle_delete_click)
        self._summary_csv_button.clicked.connect(
            self._controller.handle_summary_export_csv_click,
        )
        self._summary_md_button.clicked.connect(
            self._controller.handle_summary_export_md_click,
        )
        self._detailed_csv_button.clicked.connect(
            self._controller.handle_detailed_export_csv_click,
        )
        self._detailed_md_button.clicked.connect(
            self._controller.handle_detailed_export_md_click,
        )

    def _subscribe_to_controller_events(self) -> None:
        """
        Registers for controller state updates to keep UI synchronized.
        """
        self._controller.subscribe_to_runs_change(self._on_runs_changed)
        self._controller.subscribe_to_run_id_changed(self._on_run_id_changed)
        self._controller.subscribe_to_summary_data_change(self._on_summary_data_changed)
        self._controller.subscribe_to_detailed_data_change(self._on_detailed_data_changed)
        self._controller.subscribe_to_benchmark_status_change(
            self._on_benchmark_is_running_changed,
        )

    def _on_run_dropdown_changed(self) -> None:
        """
        Handles user selection of a different benchmark run from the dropdown.
        """
        run_id = self._run_dropdown.currentData()
        if run_id is not None:
            self._controller.handle_run_selection_change(run_id)
            logger.debug(f"Run ID selected: {run_id}")

    def _on_runs_changed(self, run_ids: list[tuple[int, str]]) -> None:
        """
        Updates the run selection dropdown with available benchmark runs.

        Args:
            run_ids: List of (run_id, run_name) tuples to populate the dropdown.
        """
        logger.debug(f"Updating runs list: {len(run_ids)} entries")
        self._run_dropdown.clear()
        for run_id, name in run_ids:
            self._run_dropdown.addItem(name, run_id)

    def _on_run_id_changed(self, run_id: int) -> None:
        """
        Syncs the dropdown selection with the currently active run ID.

        Args:
            run_id: Identifier of the run to select.
        """
        set_benchmark_run_on_dropdown(run_id, self._run_dropdown, logger)

    def _on_summary_data_changed(self, data: list[AvgSummaryTableItem]) -> None:
        """
        Updates the summary table with averaged performance metrics.

        Args:
            data: List of averaged summary items to display.
        """
        logger.debug(f"Updating summary table with {len(data)} models")
        self._update_table(
            self._summary_table,
            data,
            lambda item: [
                item.model_name,
                f"{item.avg_time_ms / 1000:.2f}",  # Convert ms to seconds
                f"{item.avg_tokens_per_second:.2f}",
                f"{item.avg_score:.2f}",
            ],
        )

    def _on_detailed_data_changed(self, data: list[SummaryTableItem]) -> None:
        """
        Updates the detailed table with per-task performance metrics.

        Args:
            data: List of detailed summary items to display.
        """
        logger.debug(f"Updating detailed table with {len(data)} tasks")
        self._update_table(
            self._detailed_table,
            data,
            lambda item: [
                item.model_name,
                item.task_id,
                item.task_status,
                str(item.time_ms),
                str(item.tokens),
                f"{item.tokens_per_second:.2f}",
                f"{item.score:.2f}",
                item.score_reason,
            ],
        )

    @staticmethod
    def _update_table(
        table: QTableWidget,
        data: list,
        row_formatter: Callable,
    ) -> None:
        """
        Generic table updater that populates a table with formatted data.

        Args:
            table: Target table to update.
            data: List of data items to display.
            row_formatter: Function that converts a data item to a list of cell values.
        """
        table.setSortingEnabled(False)
        table.setRowCount(len(data))

        for row, item in enumerate(data):
            values = row_formatter(item)
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(value))

        table.setSortingEnabled(True)

    def _on_benchmark_is_running_changed(self, is_running: bool) -> None:
        """
        Toggles UI interactivity based on benchmark execution status.

        Args:
            is_running: Current execution state of the benchmark.
        """
        logger.debug(f"Benchmark state changed: {'running' if is_running else 'stopped'}")
        enabled = not is_running
        for widget in self._benchmark_sensitive_widgets:
            widget.setEnabled(enabled)
