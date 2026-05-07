"""ChartsSwitcherWidget — QComboBox-based chart selector with 12 chart families."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QComboBox, QStackedWidget, QVBoxLayout, QWidget

from ollama_llm_bench.backend.core.interfaces import AppSettingsServiceApi
from ollama_llm_bench.backend.core.models import BenchmarkResult, BenchmarkRun
from ollama_llm_bench.backend.services.charts.aggregations import (
    Chart1TtftAggregator,
    Chart2TpsAggregator,
    Chart3TimeAggregator,
    Chart4SuccessFailedAggregator,
    Chart5PassRateAggregator,
    Chart6AvgGradeAggregator,
    Chart7VerdictCountsAggregator,
    Chart8TimeTokensAggregator,
    Chart9HeatmapAggregator,
    Chart10CategoryBarAggregator,
    Chart11SpeedQualityAggregator,
    Chart12BoxplotAggregator,
)
from ollama_llm_bench.backend.services.charts.base_chart import BaseChartAggregator
from ollama_llm_bench.ui.style.tokens import get_tokens
from ollama_llm_bench.ui.widgets.panels.result.charts.chart_frame import ChartFrame
from ollama_llm_bench.ui.widgets.panels.result.charts.heatmap_widget import HeatmapFrame

logger = logging.getLogger(__name__)

_SETTING_LAST_CHART = "ui.charts_last_chart"
_DEFAULT_CHART = "Success Rate per model"

# (display_name, aggregator_factory, chart_kind_or_"heatmap")
_CHART_REGISTRY: list[tuple[str, type[BaseChartAggregator], str]] = [
    # Performance group
    ("Avg TTFT per model", Chart1TtftAggregator, "bar"),
    ("Avg TPS per model", Chart2TpsAggregator, "bar"),
    ("Avg Time per model", Chart3TimeAggregator, "bar"),
    ("Success / Failed per model", Chart4SuccessFailedAggregator, "hbar_stacked"),
    ("Time vs Tokens", Chart8TimeTokensAggregator, "scatter"),
    ("Tokens per task (distribution)", Chart12BoxplotAggregator, "boxplot"),
    # Grading group
    ("Success Rate per model", Chart5PassRateAggregator, "bar"),
    ("Avg Grade per model", Chart6AvgGradeAggregator, "bar"),
    ("Pass / Fail counts per model", Chart7VerdictCountsAggregator, "stacked_bar"),
    ("Per-task heatmap", Chart9HeatmapAggregator, "heatmap"),
    ("Per-category bar", Chart10CategoryBarAggregator, "bar"),
    ("Speed vs Quality", Chart11SpeedQualityAggregator, "scatter"),
]

_PERF_HEADER = "── Performance ──"
_GRADING_HEADER = "── Grading ──"
_GRADING_START_NAME = "Success Rate per model"


class ChartsSwitcherWidget(QWidget):
    """12-chart selector widget using QComboBox + QStackedWidget with lazy frame creation."""

    def __init__(self, *, app_settings: AppSettingsServiceApi) -> None:
        super().__init__()
        self._app_settings = app_settings
        self._run: BenchmarkRun | None = None
        self._results: list[BenchmarkResult] = []
        self._tokens = get_tokens("dark")
        self._frame_map: dict[str, ChartFrame | HeatmapFrame] = {}
        self._name_to_stack_page: dict[str, int] = {}
        self._build_ui()
        self._restore_last_chart()

    def _build_ui(self) -> None:
        self._chart_selector = QComboBox()
        self._populate_selector()
        self._stack = QStackedWidget()
        # Pre-allocate placeholder pages for each chart
        for name, _, _ in _CHART_REGISTRY:
            placeholder = QWidget()
            page_idx = self._stack.addWidget(placeholder)
            self._name_to_stack_page[name] = page_idx

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._chart_selector)
        layout.addWidget(self._stack, 1)

        self._chart_selector.currentIndexChanged.connect(self._on_chart_selected)

    def _populate_selector(self) -> None:
        # Add Performance header
        self._chart_selector.addItem(_PERF_HEADER)
        _disable_last_item(self._chart_selector)
        for name, _, _ in _CHART_REGISTRY:
            if name == _GRADING_START_NAME:
                self._chart_selector.addItem(_GRADING_HEADER)
                _disable_last_item(self._chart_selector)
            self._chart_selector.addItem(name)

    def _restore_last_chart(self) -> None:
        raw = self._app_settings.get(_SETTING_LAST_CHART)
        target: str = raw if isinstance(raw, str) and raw else _DEFAULT_CHART
        idx = self._chart_selector.findText(target)
        if idx >= 0:
            self._chart_selector.setCurrentIndex(idx)
        else:
            # Find first non-header item
            for i in range(self._chart_selector.count()):
                if self._chart_selector.itemText(i) not in (_PERF_HEADER, _GRADING_HEADER):
                    self._chart_selector.setCurrentIndex(i)
                    break

    def update_run_data(self, run: BenchmarkRun | None, results: list[BenchmarkResult]) -> None:
        """Push new run and results to all already-instantiated chart frames."""
        self._run = run
        self._results = results
        for frame in self._frame_map.values():
            frame.update_run_data(run=run, results=results)

    def _on_chart_selected(self, index: int) -> None:
        name = self._chart_selector.itemText(index)
        if name in (_PERF_HEADER, _GRADING_HEADER, ""):
            return
        self._get_or_create_frame(name)
        page_idx = self._name_to_stack_page[name]
        self._stack.setCurrentIndex(page_idx)
        self._app_settings.set(_SETTING_LAST_CHART, name)

    def _get_or_create_frame(self, name: str) -> ChartFrame | HeatmapFrame:
        if name in self._frame_map:
            return self._frame_map[name]
        frame = _build_frame(name, self._tokens)
        frame.update_run_data(run=self._run, results=self._results)
        page_idx = self._name_to_stack_page[name]
        # Replace placeholder with real frame
        old_widget = self._stack.widget(page_idx)
        if old_widget is not None:
            self._stack.removeWidget(old_widget)
            old_widget.deleteLater()
        self._stack.insertWidget(page_idx, frame)
        self._frame_map[name] = frame
        return frame


def _is_grading(name: str) -> bool:
    grading_names = {entry[0] for entry in _CHART_REGISTRY[6:]}
    return name in grading_names


def _disable_last_item(combo: QComboBox) -> None:
    """Make the last added combo item act as a non-selectable section header."""
    raw_model = combo.model()
    if not isinstance(raw_model, QStandardItemModel):
        return
    idx = combo.count() - 1
    item = raw_model.item(idx)
    if item is None:
        return
    item.setEnabled(False)
    item.setFlags(Qt.ItemFlag.NoItemFlags)


def _build_frame(name: str, tokens: dict[str, str]) -> ChartFrame | HeatmapFrame:
    """Instantiate the correct frame type for the given chart name."""
    for entry_name, agg_cls, kind in _CHART_REGISTRY:
        if entry_name == name:
            if kind == "heatmap":
                return HeatmapFrame(aggregator=agg_cls(), tokens=tokens)
            return ChartFrame(
                aggregator=agg_cls(),
                chart_name=name,
                chart_kind=kind,  # type: ignore[arg-type]
                tokens=tokens,
            )
    raise ValueError(f"Unknown chart name: {name!r}")
