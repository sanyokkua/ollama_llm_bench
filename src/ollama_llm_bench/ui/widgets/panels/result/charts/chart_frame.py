"""ChartFrame — generic filter row + QChart canvas wrapper for all QtCharts-based charts."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QBoxPlotSeries,
    QBoxSet,
    QChart,
    QChartView,
    QHorizontalStackedBarSeries,
    QLogValueAxis,
    QScatterSeries,
    QStackedBarSeries,
    QValueAxis,
)
from PySide6.QtCore import QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.models import BenchmarkResult, BenchmarkRun
from ollama_llm_bench.backend.services.charts.base_chart import (
    BaseChartAggregator,
    ChartData,
    ChartFilters,
    FilterDescriptor,
)
from ollama_llm_bench.ui.widgets.common.multi_check_filter_button import MultiCheckFilterButton

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

ChartKind = Literal["bar", "stacked_bar", "hbar_stacked", "scatter", "boxplot"]

_EMPTY_PAGE: int = 0
_CHART_PAGE: int = 1
_EXPORT_CHART_W: int = 2400
_EXPORT_CHART_H: int = 1600
_EXPORT_CAPTION_H: int = 60

_PALETTE: tuple[str, ...] = (
    "#14B8A6",
    "#F87171",
    "#FBBF24",
    "#60A5FA",
    "#A78BFA",
    "#34D399",
    "#FB923C",
    "#E879F9",
    "#38BDF8",
    "#4ADE80",
    "#F472B6",
    "#818CF8",
)


class ChartFrame(QWidget):
    """Generic filter row + QChart canvas wrapper for all QtCharts-based charts.

    Composes a filter row derived from the aggregator's required_filters(), a
    QStackedWidget that shows either an empty-state label or a QChartView, and
    an optional footnote label below the chart.

    Attributes:
        exported: Emitted with the file path after a successful PNG export.
    """

    exported: Signal = Signal(str)

    def __init__(
        self,
        *,
        aggregator: BaseChartAggregator,
        chart_name: str,
        chart_kind: ChartKind,
        tokens: dict[str, str],
        detachable: bool = True,
    ) -> None:
        """Initialise the frame, build filter state from defaults, and build UI.

        Args:
            aggregator: Pure-Python aggregator that computes ChartData.
            chart_name: Display name used in export filenames and detached dialogs.
            chart_kind: Rendering strategy — bar, stacked_bar, hbar_stacked,
                scatter, or boxplot.
            tokens: Design token dict mapping token names to hex/value strings.
            detachable: When True (default), show the detach button and wire its
                signal.  Pass False for frames that are already inside a detached
                dialog to prevent infinite nesting.
        """
        super().__init__()
        self._aggregator: BaseChartAggregator = aggregator
        self._chart_name: str = chart_name
        self._chart_kind: ChartKind = chart_kind
        self._tokens: dict[str, str] = tokens
        self._detachable: bool = detachable
        self._run: BenchmarkRun | None = None
        self._results: list[BenchmarkResult] = []
        self._filter_state: dict[str, object] = {}
        self._multi_check_buttons: dict[str, MultiCheckFilterButton] = {}
        self._chart: QChart = QChart()
        self._chart_view: QChartView = QChartView(self._chart)
        self._stack: QStackedWidget = QStackedWidget()
        self._empty_state_label: QLabel = QLabel("No data available")
        self._footnote_label: QLabel = QLabel()
        self._export_btn: QPushButton = QPushButton("Export PNG")
        self._detach_btn: QPushButton = QPushButton("⤢")
        self._export_btn.setToolTip("Save the chart as a PNG image.")
        self._detach_btn.setToolTip("Open this chart in a separate window.")
        self._detach_btn.setVisible(self._detachable)
        self._build_filter_state()
        self._build_ui()

    # ------------------------------------------------------------------
    # Private: initialisation helpers
    # ------------------------------------------------------------------

    def _build_filter_state(self) -> None:
        """Populate _filter_state with per-descriptor defaults from the aggregator."""
        for fd in self._aggregator.required_filters():
            self._filter_state[fd.field_id] = fd.default

    def _build_ui(self) -> None:
        """Construct the full widget layout: filter row, chart stack, footnote."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(4)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # --- Filter row ---
        filter_row = QWidget()
        filter_layout = QHBoxLayout(filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(6)

        for fd in self._aggregator.required_filters():
            self._add_filter_widget(filter_layout, fd)

        filter_layout.addStretch()
        filter_layout.addWidget(self._export_btn)
        filter_layout.addWidget(self._detach_btn)

        main_layout.addWidget(filter_row)

        # --- Chart stack ---
        self._empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_state_label.setProperty("role", "secondary")

        self._build_chart()
        self._stack.addWidget(self._empty_state_label)  # page 0
        self._stack.addWidget(self._chart_view)  # page 1
        self._stack.setCurrentIndex(_EMPTY_PAGE)
        main_layout.addWidget(self._stack, 1)

        # --- Footnote ---
        self._footnote_label.setProperty("role", "secondary")
        self._footnote_label.setVisible(False)
        main_layout.addWidget(self._footnote_label)

        # --- Connections ---
        self._export_btn.clicked.connect(self._on_export_clicked)
        if self._detachable:
            self._detach_btn.clicked.connect(self._on_detach_clicked)

    def _add_filter_widget(self, layout: QHBoxLayout, fd: FilterDescriptor) -> None:
        """Append the appropriate filter widget for fd to the layout.

        Args:
            layout: The filter row layout to append into.
            fd: Descriptor defining widget kind, label, options and default.
        """
        if fd.kind == "toggle":
            checkbox = QCheckBox(fd.label)
            default_bool = bool(fd.default) if fd.default is not None else False
            checkbox.setChecked(default_bool)
            checkbox.stateChanged.connect(lambda state, fid=fd.field_id: self._on_filter_changed(fid, bool(state)))
            layout.addWidget(checkbox)
        elif fd.kind == "combo":
            layout.addWidget(QLabel(f"{fd.label}:"))
            combo = QComboBox()
            combo.addItems(list(fd.options))
            if fd.default and isinstance(fd.default, str) and fd.default in fd.options:
                combo.setCurrentText(fd.default)
            combo.currentIndexChanged.connect(
                lambda _idx, fid=fd.field_id, cb=combo: self._on_filter_changed(fid, cb.currentText())
            )
            layout.addWidget(combo)
        elif fd.kind == "multi_check":
            btn = MultiCheckFilterButton(label=fd.label)
            self._multi_check_buttons[fd.field_id] = btn
            btn.selection_changed.connect(lambda values, fid=fd.field_id: self._on_filter_changed(fid, values))
            layout.addWidget(btn)

    def _build_chart(self) -> None:
        """Configure the QChart and QChartView using design tokens for theming."""
        self._chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        self._chart.setBackgroundBrush(QColor(self._tokens.get("bg_card", "#263044")))
        self._chart.setTitleBrush(QColor(self._tokens.get("text_primary", "#F9FAFB")))
        self._chart.legend().setLabelColor(QColor(self._tokens.get("text_secondary", "#9CA3AF")))
        self._chart_view.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # ------------------------------------------------------------------
    # Private: filter change handler
    # ------------------------------------------------------------------

    def _on_filter_changed(self, field_id: str, value: object) -> None:
        """Update filter state for field_id and trigger a recompute.

        Args:
            field_id: The FilterDescriptor field identifier that changed.
            value: New value for the filter (bool, str, etc.).
        """
        self._filter_state[field_id] = value
        self._recompute_and_render()

    # ------------------------------------------------------------------
    # Public: data update
    # ------------------------------------------------------------------

    def update_run_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
    ) -> None:
        """Replace the current run and results and trigger a full re-render.

        Args:
            run: The newly selected BenchmarkRun, or None.
            results: All BenchmarkResult rows for that run.
        """
        self._run = run
        self._results = results
        self._build_filter_state()
        self._rebuild_multi_check_filters(results)
        self._refresh_multi_check_button_options()
        self._recompute_and_render()

    # ------------------------------------------------------------------
    # Private: multi-check filter rebuild
    # ------------------------------------------------------------------

    def _rebuild_multi_check_filters(self, results: list[BenchmarkResult]) -> None:
        """Rebuild frozenset values for every multi_check FilterDescriptor.

        Args:
            results: The full result list used to extract available option sets.
        """
        for fd in self._aggregator.required_filters():
            if fd.kind != "multi_check":
                continue
            if fd.field_id == "model_name":
                self._filter_state["model_name"] = frozenset(r.model_name for r in results)
            elif fd.field_id == "task_category":
                self._filter_state["task_category"] = frozenset(r.task_category for r in results)
            elif fd.field_id == "resolution_layer":
                self._filter_state["resolution_layer"] = frozenset(
                    r.resolution_layer for r in results if r.resolution_layer
                )
            elif fd.field_id == "task_id":
                self._filter_state["task_id"] = frozenset(r.task_id for r in results)
            else:
                self._filter_state[fd.field_id] = frozenset(fd.options)

    def _refresh_multi_check_button_options(self) -> None:
        """Populate each MultiCheckFilterButton with current values and counts."""
        for fd in self._aggregator.required_filters():
            if fd.kind != "multi_check":
                continue
            btn = self._multi_check_buttons.get(fd.field_id)
            if btn is None:
                continue
            if fd.field_id == "model_name":
                values = sorted({r.model_name for r in self._results})
                counts = self._counts_by(self._results, lambda r: r.model_name)
            elif fd.field_id == "task_category":
                values = sorted({r.task_category for r in self._results})
                counts = self._counts_by(self._results, lambda r: r.task_category)
            elif fd.field_id == "resolution_layer":
                values = sorted({r.resolution_layer for r in self._results if r.resolution_layer})
                counts = self._counts_by(self._results, lambda r: r.resolution_layer)
            elif fd.field_id == "task_id":
                values = sorted({r.task_id for r in self._results})
                counts = self._counts_by(self._results, lambda r: r.task_id)
            else:
                values = list(fd.options)
                counts = dict.fromkeys(values, 0)
            btn.set_options(values, counts)

    @staticmethod
    def _counts_by(
        results: list[BenchmarkResult],
        key: Callable[[BenchmarkResult], str | None],
    ) -> dict[str, int]:
        """Count result occurrences grouped by the given key function.

        Args:
            results: The full list of BenchmarkResult rows.
            key: Extracts the grouping string (or None to skip) from a result.

        Returns:
            Mapping of value string to occurrence count.
        """
        counts: dict[str, int] = {}
        for r in results:
            v = key(r)
            if v is not None:
                counts[v] = counts.get(v, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Private: filter assembly
    # ------------------------------------------------------------------

    def _build_chart_filters(self) -> ChartFilters:
        """Assemble the active filter state into a ChartFilters dataclass.

        Returns:
            Immutable ChartFilters reflecting the current widget state.
        """
        raw_models = self._filter_state.get("model_name", frozenset())
        raw_categories = self._filter_state.get("task_category", frozenset())
        raw_layers = self._filter_state.get("resolution_layer", frozenset())
        included_models: frozenset[str] = (
            frozenset(raw_models) if isinstance(raw_models, (frozenset, set)) else frozenset()
        )
        included_categories: frozenset[str] = (
            frozenset(raw_categories) if isinstance(raw_categories, (frozenset, set)) else frozenset()
        )
        included_layers: frozenset[str] = (
            frozenset(raw_layers) if isinstance(raw_layers, (frozenset, set)) else frozenset()
        )
        known_ids = {"model_name", "task_category", "resolution_layer"}
        extra: dict[str, object] = {k: v for k, v in self._filter_state.items() if k not in known_ids}
        return ChartFilters(
            included_models=included_models,
            included_categories=included_categories,
            included_layers=included_layers,
            extra=extra,
        )

    # ------------------------------------------------------------------
    # Private: recompute + render pipeline
    # ------------------------------------------------------------------

    def _recompute_and_render(self) -> None:
        """Build filters, call the aggregator, and forward the result to _render."""
        filters = self._build_chart_filters()
        data = self._aggregator.compute_data(run=self._run, results=self._results, filters=filters)
        self._render(data)

    def _render(self, data: ChartData) -> None:
        """Route aggregated ChartData to the correct renderer or show empty state.

        Args:
            data: Aggregated output from the aggregator.
        """
        if data.empty_state_message:
            self._empty_state_label.setText(data.empty_state_message)
            self._stack.setCurrentIndex(_EMPTY_PAGE)
            self._footnote_label.setVisible(False)
            return

        self._stack.setCurrentIndex(_CHART_PAGE)
        self._chart.removeAllSeries()
        for axis in self._chart.axes():
            self._chart.removeAxis(axis)

        if data.box_sets:
            self._render_boxplot(data)
        elif data.scatter_points:
            self._render_scatter(data)
        else:
            self._render_bar(data)

        if data.footnote:
            self._footnote_label.setText(data.footnote)
            self._footnote_label.setVisible(True)
        else:
            self._footnote_label.setVisible(False)

    # ------------------------------------------------------------------
    # Private: render strategies
    # ------------------------------------------------------------------

    def _render_bar(self, data: ChartData) -> None:
        """Render bar, stacked_bar, or hbar_stacked chart from series data.

        Args:
            data: Aggregated data containing series_labels, category_labels,
                and series_data tuples.
        """
        if self._chart_kind == "bar":
            series: QBarSeries | QStackedBarSeries | QHorizontalStackedBarSeries = QBarSeries()
        elif self._chart_kind == "stacked_bar":
            series = QStackedBarSeries()
        else:
            series = QHorizontalStackedBarSeries()

        for idx, (label, values) in enumerate(zip(data.series_labels, data.series_data, strict=False)):
            bar_set = QBarSet(label)
            bar_set.setColor(self._series_color(idx))
            for v in values:
                bar_set.append(v)
            series.append(bar_set)

        self._chart.addSeries(series)
        self._chart.legend().setVisible(True)
        self._chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)

        axis_color = QColor(self._tokens.get("text_secondary", "#9CA3AF"))

        if self._chart_kind == "hbar_stacked":
            cat_axis = QBarCategoryAxis()
            cat_axis.append(list(data.category_labels))
            cat_axis.setLabelsColor(axis_color)
            self._chart.addAxis(cat_axis, Qt.AlignmentFlag.AlignLeft)
            series.attachAxis(cat_axis)
            val_axis = QValueAxis()
            val_axis.setLabelsColor(axis_color)
            self._chart.addAxis(val_axis, Qt.AlignmentFlag.AlignBottom)
            series.attachAxis(val_axis)
        else:
            cat_axis = QBarCategoryAxis()
            cat_axis.append(list(data.category_labels))
            cat_axis.setLabelsColor(axis_color)
            self._chart.addAxis(cat_axis, Qt.AlignmentFlag.AlignBottom)
            series.attachAxis(cat_axis)
            val_axis = QValueAxis()
            val_axis.setLabelsColor(axis_color)
            self._chart.addAxis(val_axis, Qt.AlignmentFlag.AlignLeft)
            series.attachAxis(val_axis)

    def _render_scatter(self, data: ChartData) -> None:
        """Render a scatter plot, grouping points by their label.

        Args:
            data: Aggregated data containing scatter_points tuples of (x, y, label).
        """
        series_map: dict[str, QScatterSeries] = {}
        for point_x, point_y, label in data.scatter_points:
            if label not in series_map:
                idx = len(series_map)
                s = QScatterSeries()
                s.setName(label)
                s.setColor(self._series_color(idx))
                s.setMarkerSize(10.0)
                series_map[label] = s
            series_map[label].append(point_x, point_y)

        for s in series_map.values():
            self._chart.addSeries(s)

        self._chart.legend().setVisible(True)
        self._chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)

        axis_color = QColor(self._tokens.get("text_secondary", "#9CA3AF"))
        use_log: bool = bool(data.extra.get("log_scale", False))

        if use_log:
            x_axis: QValueAxis | QLogValueAxis = QLogValueAxis()
            y_axis: QValueAxis | QLogValueAxis = QLogValueAxis()
        else:
            x_axis = QValueAxis()
            y_axis = QValueAxis()

        if isinstance(x_axis, QValueAxis):
            x_axis.setLabelsColor(axis_color)
        if isinstance(y_axis, QValueAxis):
            y_axis.setLabelsColor(axis_color)

        self._chart.addAxis(x_axis, Qt.AlignmentFlag.AlignBottom)
        self._chart.addAxis(y_axis, Qt.AlignmentFlag.AlignLeft)
        for s in series_map.values():
            s.attachAxis(x_axis)
            s.attachAxis(y_axis)

    def _render_boxplot(self, data: ChartData) -> None:
        """Render a box-plot chart from box_sets data.

        Args:
            data: Aggregated data containing box_sets (min, q1, median, q3, max)
                tuples and series_labels for category labelling.
        """
        bp_series = QBoxPlotSeries()
        for label, box_tuple in zip(data.series_labels, data.box_sets, strict=False):
            box_min, box_q1, box_median, box_q3, box_max = box_tuple
            box_set = QBoxSet(box_min, box_q1, box_median, box_q3, box_max)
            box_set.setLabel(label)
            bp_series.append(box_set)

        self._chart.addSeries(bp_series)
        self._chart.legend().setVisible(True)
        self._chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)

        axis_color = QColor(self._tokens.get("text_secondary", "#9CA3AF"))

        cat_axis = QBarCategoryAxis()
        cat_axis.append(list(data.series_labels))
        cat_axis.setLabelsColor(axis_color)
        self._chart.addAxis(cat_axis, Qt.AlignmentFlag.AlignBottom)
        bp_series.attachAxis(cat_axis)

        val_axis = QValueAxis()
        val_axis.setLabelsColor(axis_color)
        self._chart.addAxis(val_axis, Qt.AlignmentFlag.AlignLeft)
        bp_series.attachAxis(val_axis)

    # ------------------------------------------------------------------
    # Private: color helpers
    # ------------------------------------------------------------------

    def _series_color(self, idx: int) -> QColor:
        """Return a QColor from the chart palette, cycling if idx exceeds its length.

        Args:
            idx: Zero-based series index.

        Returns:
            A QColor for the given index position in the palette.
        """
        return QColor(_PALETTE[idx % len(_PALETTE)])

    # ------------------------------------------------------------------
    # Private: export
    # ------------------------------------------------------------------

    def _on_export_clicked(self) -> None:
        """Open a save-file dialog and export the chart as a PNG if confirmed."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Chart",
            f"{self._chart_name}.png",
            "PNG (*.png)",
        )
        if path:
            self._export_png(path)

    def _export_png(self, path: str) -> None:
        """Render the QChart scene to a fixed-size QImage and save it as PNG.

        Args:
            path: Filesystem path to write the PNG to.
        """
        chart_image = QImage(_EXPORT_CHART_W, _EXPORT_CHART_H, QImage.Format.Format_ARGB32)
        chart_image.fill(QColor(self._tokens.get("bg_card", "#263044")))

        painter = QPainter(chart_image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        target_rect = QRectF(0.0, 0.0, float(_EXPORT_CHART_W), float(_EXPORT_CHART_H))
        self._chart.scene().render(
            painter,
            target_rect,
            self._chart_view.viewport().rect(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
        )
        painter.end()

        final = QPixmap(_EXPORT_CHART_W, _EXPORT_CHART_H + _EXPORT_CAPTION_H)
        final.fill(QColor(self._tokens.get("bg_card", "#263044")))

        composer = QPainter(final)
        composer.drawImage(0, 0, chart_image)

        caption_rect = QRect(0, _EXPORT_CHART_H, _EXPORT_CHART_W, _EXPORT_CAPTION_H)
        composer.setPen(QColor(self._tokens.get("text_primary", "#F9FAFB")))
        caption_font = QFont()
        caption_font.setPointSize(14)
        composer.setFont(caption_font)
        composer.drawText(caption_rect, Qt.AlignmentFlag.AlignCenter, self._caption_text())
        composer.end()

        if final.save(path):
            logger.info("Chart exported to %s", path)
            self.exported.emit(path)
        else:
            logger.warning("Failed to save chart PNG to %s", path)

    def _caption_text(self) -> str:
        """Build the caption: chart name, active-filter summary, and timestamp."""
        parts: list[str] = [self._chart_name]
        summary = self._format_filter_summary()
        if summary:
            parts.append(summary)
        parts.append(datetime.now().strftime("%Y-%m-%d %H:%M"))
        return " · ".join(parts)

    def _format_filter_summary(self) -> str:
        """Return a compact human-readable summary of which filters are active."""
        bits: list[str] = []
        models = self._filter_state.get("model_name")
        if isinstance(models, (set, frozenset)) and models:
            all_models = {r.model_name for r in self._results}
            if len(models) < len(all_models):
                bits.append(f"{len(models)}/{len(all_models)} models")
        cats = self._filter_state.get("task_category")
        if isinstance(cats, (set, frozenset)) and cats:
            all_cats = {r.task_category for r in self._results}
            if len(cats) < len(all_cats):
                bits.append(f"{len(cats)}/{len(all_cats)} categories")
        log_scale = self._filter_state.get("log_scale", False)
        if log_scale:
            bits.append("log scale")
        return ", ".join(bits)

    # ------------------------------------------------------------------
    # Private: detach
    # ------------------------------------------------------------------

    def _on_detach_clicked(self) -> None:
        """Open a non-modal dialog containing a fresh ChartFrame for this chart."""
        dialog = QDialog(self)
        dialog.setWindowTitle(self._chart_name)
        dialog.resize(900, 600)
        dialog.setMinimumSize(600, 400)

        frame = ChartFrame(
            aggregator=self._aggregator,
            chart_name=self._chart_name,
            chart_kind=self._chart_kind,
            tokens=self._tokens,
            detachable=False,
        )
        frame.update_run_data(run=self._run, results=self._results)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(frame)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(dialog.close)
        close_button = button_box.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setDefault(True)
        layout.addWidget(button_box)

        dialog.show()
