from __future__ import annotations

import logging

from PySide6.QtWidgets import QFrame, QSizePolicy, QVBoxLayout, QWidget

from ollama_llm_bench.backend.core.interfaces import AppSettingsServiceApi, BenchmarkFlowApi, EventBus
from ollama_llm_bench.ui.widgets.panels.progress_panel_widget import ProgressPanelWidget
from ollama_llm_bench.ui.widgets.panels.result.log_widget import LogWidget

logger = logging.getLogger(__name__)


class CenterPanel(QWidget):
    """Center panel composing ProgressPanelWidget (top) and LogWidget (bottom)."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        benchmark_flow_api: BenchmarkFlowApi,
        app_settings: AppSettingsServiceApi,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._progress_panel = ProgressPanelWidget(
            event_bus=event_bus,
            benchmark_flow_api=benchmark_flow_api,
            app_settings=app_settings,
        )
        self._progress_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        self._log_widget = LogWidget(event_bus=event_bus, app_settings=app_settings)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self._progress_panel)
        layout.addWidget(separator)
        layout.addWidget(self._log_widget, 1)
