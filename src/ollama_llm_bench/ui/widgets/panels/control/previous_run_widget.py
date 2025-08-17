import logging
from typing import List, Tuple

from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.core.ui_controllers import PreviousRunWidgetControllerApi
from ollama_llm_bench.utils.widget_utils import set_benchmark_run_on_dropdown

logger = logging.getLogger(__name__)


class PreviousRunWidget(QWidget):
    """
    UI component for selecting and continuing previously started benchmark runs.
    Displays unfinished runs and provides controls to resume or stop execution.
    """

    def __init__(self, controller: PreviousRunWidgetControllerApi) -> None:
        """
        Initialize the previous run widget.

        Args:
            controller: Controller API for handling user interactions.
        """
        super().__init__()
        self._controller = controller
        self._setup_ui()
        self._setup_signals()

    def _setup_ui(self) -> None:
        """
        Initialize and arrange all UI components in a structured layout.
        Creates sections for run selection and action buttons.
        """
        # Create core widgets with consistent naming
        self._refresh_button = QPushButton("Refresh Runs")
        self._start_button = QPushButton("Continue Benchmark")
        self._stop_button = QPushButton("Stop Benchmark")
        self._unfinished_dropdown = QComboBox()

        # Configure unfinished runs section
        unfinished_group = QGroupBox("Unfinished Benchmarks")
        unfinished_layout = QVBoxLayout()
        unfinished_layout.addWidget(self._unfinished_dropdown)
        unfinished_group.setLayout(unfinished_layout)

        # Organize action buttons
        button_layout = QHBoxLayout()
        button_layout.addWidget(self._refresh_button)
        button_layout.addWidget(self._start_button)
        button_layout.addWidget(self._stop_button)

        # Assemble main layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(unfinished_group)
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

    def _setup_signals(self) -> None:
        """
        Connect all UI signals to controller handlers and event subscriptions.
        """
        self._start_button.clicked.connect(self._controller.handle_start_click)
        self._refresh_button.clicked.connect(self._controller.handle_refresh_click)
        self._stop_button.clicked.connect(self._controller.handle_stop_click)
        self._unfinished_dropdown.currentIndexChanged.connect(
            self._handle_dropdown_selection,
        )

        # Subscribe to controller events
        self._controller.subscribe_to_runs_change(self._update_runs_dropdown)
        self._controller.subscribe_to_run_id_changed(self._update_selected_run)
        self._controller.subscribe_to_benchmark_status_change(
            self._update_ui_for_benchmark_status,
        )

    def _handle_dropdown_selection(self) -> None:
        """
        Handle user selection of a different benchmark run from the dropdown.
        """
        current_index = self._unfinished_dropdown.currentIndex()
        if current_index < 0:
            logger.debug("Dropdown index changed to invalid state")
            return

        run_id = self._unfinished_dropdown.itemData(current_index)
        if run_id is None:
            logger.warning("Selected dropdown item has no run ID data")
            return

        logger.debug(f"Dropdown selection changed to run ID: {run_id}")
        self._controller.handle_item_change(run_id)

    def _update_runs_dropdown(self, runs: List[Tuple[int, str]]) -> None:
        """
        Update the dropdown list with available unfinished benchmark runs.

        Args:
            runs: List of (run_id, run_name) tuples to populate the dropdown.
        """
        logger.debug(f"Updating runs dropdown with {len(runs)} runs")
        # Temporarily block signals to avoid triggering during population
        self._unfinished_dropdown.blockSignals(True)
        self._unfinished_dropdown.clear()

        # Use declarative approach for population
        for run_id, name in runs:
            self._unfinished_dropdown.addItem(name, run_id)

        self._unfinished_dropdown.blockSignals(False)

        # Restore previous selection if possible
        if runs and self._unfinished_dropdown.count() > 0:
            self._unfinished_dropdown.setCurrentIndex(0)

    def _update_selected_run(self, run_id: int) -> None:
        """
        Update the dropdown to reflect the currently selected benchmark run.

        Args:
            run_id: Identifier of the run to select.
        """
        logger.debug(f"Updating dropdown to show run ID: {run_id}")
        set_benchmark_run_on_dropdown(run_id, self._unfinished_dropdown, logger)

    def _update_ui_for_benchmark_status(self, is_running: bool) -> None:
        """
        Update UI state based on current benchmark execution status.

        Args:
            is_running: Current execution state of the benchmark.
        """
        logger.debug(f"Updating UI for benchmark status: {'running' if is_running else 'stopped'}")

        # Group widgets by their enabled state logic
        self._set_widgets_enabled(
            widgets=[self._unfinished_dropdown, self._refresh_button, self._start_button],
            enabled=not is_running,
        )
        self._stop_button.setEnabled(is_running)

    @staticmethod
    def _set_widgets_enabled(widgets: List[QWidget], enabled: bool) -> None:
        """
        Helper method to batch-configure widget enabled states.

        Args:
            widgets: List of widgets to update.
            enabled: Desired enabled state.
        """
        for widget in widgets:
            widget.setEnabled(enabled)
