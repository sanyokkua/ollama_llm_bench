import logging
from typing import List

from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.core.models import NewRunWidgetStartEvent
from ollama_llm_bench.core.ui_controllers import NewRunWidgetControllerApi

logger = logging.getLogger(__name__)


class NewRunWidget(QWidget):
    """
    UI component for configuring and starting new benchmark runs.
    Allows selection of judge model, test models, and controls execution.
    """

    def __init__(self, controller: NewRunWidgetControllerApi) -> None:
        """
        Initialize the new run widget.

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
        Creates sections for judge model selection, test model selection, and action buttons.
        """
        # Create core widgets with consistent naming
        self._judge_dropdown = QComboBox()
        self._models_list = QListWidget()
        self._refresh_button = QPushButton("Refresh Models")
        self._start_button = QPushButton("Start Benchmark")
        self._stop_button = QPushButton("Stop Benchmark")

        # Configure multi-selection mode immediately during setup
        self._models_list.setSelectionMode(
            QListWidget.SelectionMode.MultiSelection,
        )

        # Organize judge selection section
        judge_group = QGroupBox("Judge Model")
        judge_layout = QVBoxLayout()
        judge_layout.addWidget(self._judge_dropdown)
        judge_group.setLayout(judge_layout)

        # Organize models section
        models_group = QGroupBox("Models to Benchmark")
        models_layout = QVBoxLayout()
        models_layout.addWidget(self._models_list)
        models_group.setLayout(models_layout)

        # Organize action buttons
        button_layout = QHBoxLayout()
        button_layout.addWidget(self._refresh_button)
        button_layout.addWidget(self._start_button)
        button_layout.addWidget(self._stop_button)

        # Assemble main layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(judge_group)
        main_layout.addWidget(models_group)
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

    def _setup_signals(self) -> None:
        """
        Connect all UI signals to controller handlers and event subscriptions.
        """
        self._start_button.clicked.connect(self._handle_start_click)
        self._refresh_button.clicked.connect(self._controller.handle_refresh_click)
        self._stop_button.clicked.connect(self._controller.handle_stop_click)

        # Subscribe to controller events
        self._controller.subscribe_to_models_change(self._update_model_lists)
        self._controller.subscribe_to_benchmark_status_change(
            self._update_ui_for_benchmark_status,
        )

    def _handle_start_click(self) -> None:
        """
        Handle user request to start a new benchmark run.
        Collects selected models and judge configuration and forwards to controller.
        """
        logger.debug("Start Benchmark button clicked")
        # Preserve selection order and avoid unnecessary set conversion
        selected_models = [
            item.text() for item in self._models_list.selectedItems()
        ]

        event = NewRunWidgetStartEvent(
            judge_model=self._judge_dropdown.currentText(),
            models=tuple(selected_models),
        )
        self._controller.handle_start_click(event)

    def _update_model_lists(self, models: List[str]) -> None:
        """
        Update both judge dropdown and models list with available models.

        Args:
            models: List of model names to populate in UI.
        """
        logger.debug(f"Updating model lists with {len(models)} models")
        # Clear and repopulate both widgets in single operation
        self._judge_dropdown.clear()
        self._models_list.clear()

        if models:
            self._judge_dropdown.addItems(models)
            self._models_list.addItems(models)

    def _update_ui_for_benchmark_status(self, is_running: bool) -> None:
        """
        Update UI state based on current benchmark execution status.

        Args:
            is_running: Current execution state of the benchmark.
        """
        logger.debug(f"Updating UI for benchmark status: {'running' if is_running else 'stopped'}")

        # Group widgets by their enabled state logic
        self._set_widgets_enabled(
            widgets=[self._judge_dropdown, self._models_list, self._refresh_button],
            enabled=not is_running,
        )
        self._start_button.setEnabled(not is_running)
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
