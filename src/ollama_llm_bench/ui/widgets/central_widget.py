import logging
from typing import Final

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from ollama_llm_bench.core.interfaces import AppContext
from ollama_llm_bench.ui.widgets.panels.control_panel import ControlPanel
from ollama_llm_bench.ui.widgets.panels.results_panel import ResultsPanel

logger = logging.getLogger(__name__)

# Constants for layout configuration
_CONTROL_PANEL_WEIGHT: Final[int] = 20  # Percentage of total width
_RESULTS_PANEL_WEIGHT: Final[int] = 80  # Percentage of total width
_MIN_SPLITTER_SIZE: Final[int] = 100  # Minimum pixels for control panel


class CentralWidget(QWidget):
    """Primary application container with resizable control/results layout.
    
    Implements a flexible two-pane interface where:
    - Left pane: ControlPanel for benchmark configuration and execution
    - Right pane: ResultsPanel for visualization of benchmark outcomes
    
    The splitter maintains proportional sizing while respecting minimum dimensions,
    providing optimal workspace allocation for both interaction and results viewing.
    """

    def __init__(self, ctx: AppContext) -> None:
        """Initialize the main application container with context.
        
        Args:
            ctx: Application context providing access to controllers and services
            
        Raises:
            RuntimeError: If critical panels fail to initialize
        """
        super().__init__()
        logger.debug("Initializing CentralWidget")

        self._control_panel: ControlPanel = ControlPanel(ctx)
        self._results_panel: ResultsPanel = ResultsPanel(ctx)

        # Configure the main layout
        self._setup_layout()

        logger.info(
            "CentralWidget initialized with %d/%d layout ratio",
            _CONTROL_PANEL_WEIGHT,
            _RESULTS_PANEL_WEIGHT,
        )

    def _setup_layout(self) -> None:
        """Configures the resizable splitter layout with proportional sizing."""
        # Create horizontal splitter with proper orientation constant
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._control_panel)
        splitter.addWidget(self._results_panel)

        # Set minimum size constraint for control panel
        splitter.setSizes(self._calculate_splitter_sizes())
        splitter.setMinimumWidth(_MIN_SPLITTER_SIZE)

        # Configure main layout
        layout = QVBoxLayout()
        layout.addWidget(splitter)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)  # Eliminate unnecessary gaps
        self.setLayout(layout)

    @staticmethod
    def _calculate_splitter_sizes() -> list[int]:
        """Calculate initial splitter sizes based on weight ratios.

        Returns:
            List containing [control_panel_size, results_panel_size]
        """
        # Use a reasonable total width for ratio calculation
        total_width = _MIN_SPLITTER_SIZE * 10  # 1000px reference width

        # Calculate proportional sizes
        control_size = max(
            _MIN_SPLITTER_SIZE,
            int(total_width * _CONTROL_PANEL_WEIGHT / 100),
        )
        results_size = total_width - control_size

        return [control_size, results_size]
