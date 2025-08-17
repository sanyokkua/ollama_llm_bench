from typing import Final

from PyQt6.QtWidgets import QTabWidget

from ollama_llm_bench.core.interfaces import AppContext
from ollama_llm_bench.ui.widgets.panels.control.new_run_widget import NewRunWidget
from ollama_llm_bench.ui.widgets.panels.control.previous_run_widget import PreviousRunWidget

_TAB_TITLE_NEW: Final[str] = "Run New Benchmark"
_TAB_TITLE_PREVIOUS: Final[str] = "Run Previous Benchmark"


class ControlTabWidget(QTabWidget):
    """
    Tab container for benchmark control panels with centralized configuration.
    Manages the 'New Run' and 'Previous Run' tabs with proper UI separation.
    """

    def __init__(self, ctx: AppContext) -> None:
        """
        Initialize the control tab widget.

        Args:
            ctx: Application context providing access to controller APIs.
        """
        super().__init__()
        self._setup_tabs(ctx)

    def _setup_tabs(self, ctx: AppContext) -> None:
        """
        Initialize and configure all tab pages with proper separation of concerns.

        Args:
            ctx: Application context for retrieving widget controller APIs.
        """
        # Create widgets with explicit type annotations
        new_run_widget: NewRunWidget = NewRunWidget(
            ctx.get_new_run_widget_controller_api(),
        )
        previous_run_widget: PreviousRunWidget = PreviousRunWidget(
            ctx.get_previous_run_widget_controller_api(),
        )

        # Add tabs with centralized titles
        self.addTab(new_run_widget, _TAB_TITLE_NEW)
        self.addTab(previous_run_widget, _TAB_TITLE_PREVIOUS)

        # Optional: Set default tab (first tab is default in QTabWidget)
        self.setCurrentIndex(0)
