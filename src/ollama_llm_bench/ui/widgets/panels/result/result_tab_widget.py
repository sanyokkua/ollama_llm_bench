import logging
from typing import Final

from PyQt6.QtWidgets import QTabWidget

from ollama_llm_bench.core.interfaces import AppContext, EventBus
from ollama_llm_bench.ui.widgets.panels.result.log_widget import LogWidget
from ollama_llm_bench.ui.widgets.panels.result.result_widget import ResultWidget

logger = logging.getLogger(__name__)

_LOG_TAB_LABEL: Final[str] = "System Log"
_RESULT_TAB_LABEL: Final[str] = "Results"


class ResultTabWidget(QTabWidget):
    """
    Tab container for benchmark result and log displays with dynamic behavior.
    Automatically switches to log tab during execution and prevents tab changes.
    """

    def __init__(self, ctx: AppContext) -> None:
        """
        Initialize the result tab widget.

        Args:
            ctx: Application context providing access to controller APIs and event bus.
        """
        super().__init__()
        # Add explicit type hints for better static analysis
        self._event_bus: EventBus = ctx.get_event_bus()
        self._log_tab: LogWidget = LogWidget(ctx.get_log_widget_controller_api())
        self._result_tab: ResultWidget = ResultWidget(ctx.get_result_widget_controller_api())

        # Use constants for tab labels (DRY principle)
        self.addTab(self._log_tab, _LOG_TAB_LABEL)
        self.addTab(self._result_tab, _RESULT_TAB_LABEL)

        # Subscribe to benchmark state changes
        self._event_bus.subscribe_to_background_thread_is_running(
            self._on_benchmark_is_running_changed,
        )
        logger.debug("ResultTabWidget initialized with EventBus subscription")

    def _on_benchmark_is_running_changed(self, is_running: bool) -> None:
        """
        Update UI state based on benchmark execution status.

        Args:
            is_running: Current execution state of the benchmark.
        """
        logger.debug(f"Benchmark execution state changed: {'running' if is_running else 'stopped'}")

        if is_running:
            # Force log tab visibility during execution
            self.setCurrentIndex(0)  # Log tab is always index 0 (KISS principle)
            self.tabBar().setEnabled(False)  # Disables ALL interactions (simpler & correct)
        else:
            self.tabBar().setEnabled(True)  # Restore full tab functionality
