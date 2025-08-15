import logging

from PyQt6.QtWidgets import QTabWidget

from ollama_llm_bench.core.interfaces import AppContext
from ollama_llm_bench.ui.widgets.panels.result.log_widget import LogWidget
from ollama_llm_bench.ui.widgets.panels.result.result_widget import ResultWidget

logger = logging.getLogger(__name__)


class ResultTabWidget(QTabWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._event_bus = ctx.get_event_bus()

        self._log_tab = LogWidget(ctx.get_log_widget_controller_api())
        self._result_tab = ResultWidget(ctx.get_result_widget_controller_api())

        self.addTab(self._log_tab, "System Log")
        self.addTab(self._result_tab, "Results")

        self._event_bus.subscribe_to_background_thread_is_running(self._on_benchmark_is_running_changed)

    def _on_benchmark_is_running_changed(self, is_running: bool) -> None:
        logger.debug(f"Benchmark is running: {is_running}")
        if is_running:
            self.setCurrentIndex(self.indexOf(self._log_tab))
            self.tabBar().setTabsClosable(False)
            self.tabBar().setMovable(False)
            self.tabBar().setEnabled(False)
        else:
            self.tabBar().setEnabled(True)
