import logging
from typing import Final, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from ollama_llm_bench.backend.core.interfaces import AppContext
from ollama_llm_bench.backend.core.models import (
    BenchmarkFinishedEvent,
    BenchmarkStartedEvent,
    BenchmarkStoppedEvent,
)
from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController
from ollama_llm_bench.ui.widgets.panels.center_panel import CenterPanel
from ollama_llm_bench.ui.widgets.panels.results_panel import ResultsPanel
from ollama_llm_bench.ui.widgets.panels.run_config_panel import RunConfigPanel

logger = logging.getLogger(__name__)

_LEFT_DEFAULT_WIDTH: Final[int] = 360
_CENTER_DEFAULT_WIDTH: Final[int] = 520
_RIGHT_DEFAULT_WIDTH: Final[int] = 440
_LEFT_MIN_WIDTH: Final[int] = 280
_CENTER_MIN_WIDTH: Final[int] = 320
_RIGHT_MIN_WIDTH: Final[int] = 380


class CentralWidget(QWidget):
    """Primary application container with 3-panel resizable layout.

    Left: RunConfigPanel — mode, provider, model, task file, action buttons.
    Center: CenterPanel — progress widget + log.
    Right: ResultsPanel — benchmark result tables.
    """

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        logger.debug("Initializing CentralWidget")
        self._event_bus = ctx.get_event_bus()
        self._pre_run_sizes: list[int] = []

        self._run_config_panel = RunConfigPanel(controller=cast(RunConfigController, ctx.get_run_config_controller()))
        self._run_config_panel.setMinimumWidth(_LEFT_MIN_WIDTH)

        self._center_panel = CenterPanel(
            event_bus=ctx.get_event_bus(),
            benchmark_flow_api=ctx.get_benchmark_flow_api(),
            app_settings=ctx.get_app_settings_service(),
            run_config_controller=ctx.get_run_config_controller(),
        )
        self._center_panel.setMinimumWidth(_CENTER_MIN_WIDTH)

        self._results_panel = ResultsPanel(controller=ctx.get_result_widget_controller_api())
        self._results_panel.setMinimumWidth(_RIGHT_MIN_WIDTH)

        self._setup_layout()
        self._event_bus.subscribe_to_benchmark_started(self._on_benchmark_started, parent=self)
        self._event_bus.subscribe_to_benchmark_finished(self._on_benchmark_finished, parent=self)
        self._event_bus.subscribe_to_benchmark_stopped(self._on_benchmark_stopped, parent=self)
        logger.info("CentralWidget initialized with 3-panel layout")

    def _setup_layout(self) -> None:
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._run_config_panel)
        self._splitter.addWidget(self._center_panel)
        self._splitter.addWidget(self._results_panel)
        self._splitter.setSizes([_LEFT_DEFAULT_WIDTH, _CENTER_DEFAULT_WIDTH, _RIGHT_DEFAULT_WIDTH])

        layout = QVBoxLayout(self)
        layout.addWidget(self._splitter)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

    def _on_benchmark_started(self, _event: BenchmarkStartedEvent) -> None:
        self._pre_run_sizes = self._splitter.sizes()
        self._splitter.setSizes([0, *self._pre_run_sizes[1:]])

    def _on_benchmark_finished(self, _event: BenchmarkFinishedEvent) -> None:
        self._restore_splitter()

    def _on_benchmark_stopped(self, _event: BenchmarkStoppedEvent) -> None:
        self._restore_splitter()

    def _restore_splitter(self) -> None:
        if self._pre_run_sizes:
            self._splitter.setSizes(self._pre_run_sizes)
            self._pre_run_sizes = []
