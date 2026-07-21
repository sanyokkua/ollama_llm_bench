"""``ChartsTabView`` -- the Charts tab's passive Qt view (STORY-064).

Source of truth: ``docs/v3_specification/05_Result_Widget/tabs/charts_tab.md`` §2
(layout), §5 (global filter chips), §6 (per-chart options), §7 (navigation and the
chart-kind dropdown), §8 (chart-click drill-down). Passive View: renders a
``ChartsViewModel`` via ``apply()`` and emits widget-local Qt signals on user
interaction; imports no adapter Gateway, no reactive store, and no backend
service symbol beyond ``backend.domain`` DTOs/enums it renders.

**Documented scope simplification** (see the story's Notes section): chart-click
drill-down hit-testing is implemented for the per-model bar (charts 1, 2, 3, 5, 6),
stacked-segment (charts 4, 7), grouped sub-bar (chart 10), heatmap cell (chart 9),
and scatter-point (charts 8, 11) element kinds; the box-plot outlier marker (chart
12) is not click-mapped in this pass -- charts_tab.md#8's row for chart 12 is not
exercised by any of this story's acceptance criteria.
"""

from functools import partial
from typing import override

from PySide6.QtCore import QPointF, QRectF, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.domain import ChartKind, HeatmapData
from ollama_llm_bench.ui.results._internal.charts_tab import drilldown, painting
from ollama_llm_bench.ui.results._internal.theme_lookup import (
    resolve_spacing_tokens,
    resolve_theme_tokens,
)
from ollama_llm_bench.ui.results.models import (
    ChartDrilldownRequest,
    ChartOptionControl,
    ChartsViewModel,
)
from ollama_llm_bench.ui.theme import (
    PlatformKind,
    ThemeManager,
    ThemeTokens,
    make_dark_theme_tokens,
)

__all__: list[str] = ["ChartsTabView"]

_STACKED_KINDS = frozenset(
    {ChartKind.SUCCESS_FAILED_INCOMPLETE_STACKED, ChartKind.VERDICT_COUNTS_STACKED}
)
_BAR_KINDS = frozenset(
    {
        ChartKind.AVG_TTFT_PER_MODEL,
        ChartKind.AVG_TPS_PER_MODEL,
        ChartKind.AVG_TIME_PER_MODEL,
        ChartKind.PASS_RATE_BY_MODEL,
        ChartKind.AVG_COSINE_BY_MODEL,
    }
)
_SCATTER_KINDS = frozenset({ChartKind.TIME_VS_TOKENS_SCATTER, ChartKind.SPEED_VS_QUALITY_SCATTER})
_POINT_HIT_RADIUS = 12.0
_NO_DATA_SUFFIX = " (no data)"
_MIN_XY_SERIES = 2


class _FilterChipButton(QPushButton):
    """A checkable multi-select filter chip: label ``"<Label> N / M"``, default
    all-checked (charts_tab.md#5). Mirrors ``details_tab``'s/``summary_tab``'s
    identical chip pattern."""

    selection_changed = Signal(object)  # tuple[str, ...]

    def __init__(self, *, object_suffix: str, label: str) -> None:
        super().__init__()
        self.setObjectName(f"charts_tab.filters.{object_suffix}")
        self._label = label
        self._options: tuple[str, ...] = ()
        self._checked: set[str] = set()
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self._refresh_label()

    def set_options(self, options: tuple[str, ...], *, checked: tuple[str, ...]) -> None:
        self._options = options
        self._checked = set(options) if not checked else set(checked)
        self._menu.clear()
        for value in options:
            action = self._menu.addAction(value)
            action.setCheckable(True)
            action.setChecked(value in self._checked)
            action.toggled.connect(partial(self._on_option_toggled, value))
        self._refresh_label()

    def _on_option_toggled(self, value: str, checked: bool) -> None:  # noqa: FBT001  # Qt signal callback
        if checked:
            self._checked.add(value)
        else:
            self._checked.discard(value)
        self._refresh_label()
        self.selection_changed.emit(tuple(v for v in self._options if v in self._checked))

    def _refresh_label(self) -> None:
        self.setText(f"{self._label} {len(self._checked)} / {len(self._options)}")


class _ChartCanvas(QWidget):
    """The chart-drawing surface: dispatches to ``painting.draw_*`` and hit-tests
    a click against the geometry it just painted (charts_tab.md#8)."""

    element_clicked = Signal(object)  # ChartDrilldownRequest

    def __init__(self, *, platform_kind: PlatformKind, theme_manager: ThemeManager | None) -> None:
        super().__init__()
        self.setObjectName("charts_tab.canvas")
        self._platform_kind = platform_kind
        self._theme_manager = theme_manager
        self._view_model: ChartsViewModel | None = None
        self._no_run_message: str | None = None
        self._hit_regions: list[tuple[QRectF, ChartDrilldownRequest]] = []
        self._point_regions: list[tuple[QPointF, ChartDrilldownRequest]] = []
        self.setMinimumHeight(240)

    def apply(self, view_model: ChartsViewModel) -> None:
        self._view_model = view_model
        self._no_run_message = None
        self.update()

    def apply_no_run(self, message: str) -> None:
        self._view_model = None
        self._no_run_message = message
        self.update()

    def _tokens(self) -> ThemeTokens:
        if self._theme_manager is not None:
            return resolve_theme_tokens(
                theme_manager=self._theme_manager, platform_kind=self._platform_kind
            )
        return make_dark_theme_tokens(platform_kind=self._platform_kind)

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        tokens = self._tokens()
        rect = QRectF(0, 0, self.width(), self.height())
        self._hit_regions = []
        self._point_regions = []
        vm = self._view_model
        if vm is None:
            if self._no_run_message is not None:
                painting.draw_empty_state(
                    painter, rect=rect, message=self._no_run_message, tokens=tokens
                )
            painter.end()
            return
        if vm.empty_state_message is not None:
            painting.draw_empty_state(
                painter, rect=rect, message=vm.empty_state_message, tokens=tokens
            )
            painter.end()
            return
        if vm.heatmap_data is not None:
            self._paint_heatmap(painter, rect=rect, data=vm.heatmap_data, tokens=tokens)
        elif vm.chart_data is not None:
            self._paint_chart_data(painter, rect=rect, tokens=tokens, vm=vm)
        painter.end()

    def _paint_chart_data(
        self, painter: QPainter, *, rect: QRectF, tokens: ThemeTokens, vm: ChartsViewModel
    ) -> None:
        data = vm.chart_data
        assert data is not None  # noqa: S101  # narrowed by the caller's `vm.chart_data is not None` check
        if vm.chart_kind in _STACKED_KINDS:
            painting.draw_stacked_bar_chart(
                painter, rect=rect, data=data, tokens=tokens, hidden_series=vm.hidden_series
            )
            self._index_stacked_hits(rect=rect, vm=vm)
            return
        if vm.chart_kind in _BAR_KINDS:
            painting.draw_bar_chart(painter, rect=rect, data=data, tokens=tokens)
            self._index_bar_hits(rect=rect, vm=vm)
            return
        if vm.chart_kind is ChartKind.PER_CATEGORY_BAR:
            painting.draw_grouped_bar_chart(painter, rect=rect, data=data, tokens=tokens)
            self._index_grouped_bar_hits(rect=rect, vm=vm)
            return
        if vm.chart_kind in _SCATTER_KINDS:
            painting.draw_scatter_chart(painter, rect=rect, data=data, tokens=tokens)
            self._index_scatter_hits(rect=rect, vm=vm)
            return
        if vm.chart_kind is ChartKind.TOKENS_PER_TASK_BOX:
            painting.draw_box_plot(painter, rect=rect, data=data, tokens=tokens)

    def _paint_heatmap(
        self, painter: QPainter, *, rect: QRectF, data: HeatmapData, tokens: ThemeTokens
    ) -> None:
        painting.draw_heatmap(painter, rect=rect, data=data, tokens=tokens)
        self._index_heatmap_hits(rect=rect, data=data)

    def _resolve_model(self, vm: ChartsViewModel, label: str) -> tuple[str, str] | None:
        for provider_id, model_name, provider_name in vm.filter_domains.models:
            if f"{provider_name} / {model_name}" == label:
                return provider_id, model_name
        return None

    def _plot_rect(self, rect: QRectF) -> QRectF:
        pad = min(rect.width(), rect.height()) * 0.08
        return rect.adjusted(pad, pad, -pad, -pad)

    def _index_bar_hits(self, *, rect: QRectF, vm: ChartsViewModel) -> None:
        data = vm.chart_data
        if data is None or not data.categories:
            return
        plot = self._plot_rect(rect)
        group_width = plot.width() / max(len(data.categories), 1)
        for index, label in enumerate(data.categories):
            model = self._resolve_model(vm, label)
            if model is None:
                continue
            bar_rect = QRectF(
                plot.left() + index * group_width, plot.top(), group_width, plot.height()
            )
            request = drilldown.map_bar_click(
                chart_kind=vm.chart_kind, provider_id=model[0], model_name=model[1]
            )
            self._hit_regions.append((bar_rect, request))

    def _index_stacked_hits(self, *, rect: QRectF, vm: ChartsViewModel) -> None:
        data = vm.chart_data
        if data is None or not data.categories:
            return
        plot = self._plot_rect(rect)
        group_width = plot.width() / max(len(data.categories), 1)
        visible_series = tuple(s for s in data.series if s.name not in vm.hidden_series)
        for index, label in enumerate(data.categories):
            model = self._resolve_model(vm, label)
            if model is None or not visible_series:
                continue
            column_rect = QRectF(
                plot.left() + index * group_width, plot.top(), group_width, plot.height()
            )
            segment = visible_series[0].name
            request = drilldown.map_stacked_segment_click(
                chart_kind=vm.chart_kind, provider_id=model[0], model_name=model[1], segment=segment
            )
            self._hit_regions.append((column_rect, request))

    def _index_grouped_bar_hits(self, *, rect: QRectF, vm: ChartsViewModel) -> None:
        data = vm.chart_data
        if data is None or not data.categories or not data.series:
            return
        plot = self._plot_rect(rect)
        group_width = plot.width() / max(len(data.categories), 1)
        series_width = group_width / max(len(data.series), 1)
        for cat_index, category in enumerate(data.categories):
            for series_index, series in enumerate(data.series):
                model = self._resolve_model(vm, series.name)
                if model is None:
                    continue
                cell_rect = QRectF(
                    plot.left() + cat_index * group_width + series_index * series_width,
                    plot.top(),
                    series_width,
                    plot.height(),
                )
                request = drilldown.map_grouped_bar_click(
                    provider_id=model[0], model_name=model[1], category=category
                )
                self._hit_regions.append((cell_rect, request))

    def _index_heatmap_hits(self, *, rect: QRectF, data: HeatmapData) -> None:
        if not data.row_labels or not data.column_labels:
            return
        vm = self._view_model
        if vm is None:
            return
        plot = self._plot_rect(rect)
        cell_width = plot.width() / len(data.column_labels)
        cell_height = plot.height() / len(data.row_labels)
        for row_index, task_id in enumerate(data.row_labels):
            for col_index, column_label in enumerate(data.column_labels):
                model = self._resolve_model(vm, column_label)
                if model is None:
                    continue
                cell_rect = QRectF(
                    plot.left() + col_index * cell_width,
                    plot.top() + row_index * cell_height,
                    cell_width,
                    cell_height,
                )
                request = drilldown.map_heatmap_cell_click(
                    provider_id=model[0], model_name=model[1], task_id=task_id
                )
                self._hit_regions.append((cell_rect, request))

    def _index_scatter_hits(self, *, rect: QRectF, vm: ChartsViewModel) -> None:
        data = vm.chart_data
        if data is None or not data.categories or len(data.series) < _MIN_XY_SERIES:
            return
        plot = self._plot_rect(rect)
        x_series, y_series = data.series[0], data.series[1]
        axis_range = painting.finite_axis_range(x_series.values, y_series.values)
        if axis_range is None:
            return
        for index, label in enumerate(data.categories):
            model = self._resolve_model(vm, label)
            x_value = x_series.values[index] if index < len(x_series.values) else None
            y_value = y_series.values[index] if index < len(y_series.values) else None
            if model is None or x_value is None or y_value is None:
                continue
            point = painting.scale_point(plot, x_value, y_value, axis_range)
            task_id = (
                str(data.series[0].result_ids[index])
                if index < len(data.series[0].result_ids)
                else ""
            )
            request = drilldown.map_scatter_point_click(
                chart_kind=vm.chart_kind, provider_id=model[0], model_name=model[1], task_id=task_id
            )
            self._point_regions.append((point, request))

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        position = event.position()
        for point, request in self._point_regions:
            if (point - position).manhattanLength() <= _POINT_HIT_RADIUS:
                self.element_clicked.emit(request)
                return
        for hit_rect, request in self._hit_regions:
            if hit_rect.contains(position):
                self.element_clicked.emit(request)
                return


class ChartsTabView(QWidget):
    """Passive Charts tab body: navigation toolbar, filter chips, per-chart
    options, the chart canvas, and detach (charts_tab.md#2)."""

    prev_clicked = Signal()
    next_clicked = Signal()
    chart_kind_selected = Signal(str)
    filter_changed = Signal(str, list)
    option_changed = Signal(str, str)
    legend_series_toggled = Signal(str)
    clear_filters_clicked = Signal()
    detach_clicked = Signal()
    chart_element_clicked = Signal(object)  # ChartDrilldownRequest

    def __init__(
        self,
        *,
        platform_kind: PlatformKind = PlatformKind.UNKNOWN,
        theme_manager: ThemeManager | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("charts_tab.view")
        self._platform_kind = platform_kind
        self._theme_manager = theme_manager
        self._build_ui()

    def _build_ui(self) -> None:
        tokens = resolve_spacing_tokens(platform_kind=self._platform_kind)
        spacing = tokens.spacing
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(spacing.sm)

        root.addLayout(self._build_nav_bar(spacing_px=spacing.sm))
        root.addWidget(self._build_filter_bar(spacing_px=spacing.sm))

        self._meta_line_label = QLabel("")
        self._meta_line_label.setObjectName("charts_tab.meta_line")
        root.addWidget(self._meta_line_label)

        self._canvas = _ChartCanvas(
            platform_kind=self._platform_kind, theme_manager=self._theme_manager
        )
        self._canvas.element_clicked.connect(self.chart_element_clicked)
        root.addWidget(self._canvas, 1)

    def _build_nav_bar(self, *, spacing_px: int) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(spacing_px)
        self._prev_button = QPushButton("<")
        self._prev_button.setObjectName("charts_tab.nav.prev")
        self._prev_button.setToolTip("Previous chart")
        self._prev_button.clicked.connect(self.prev_clicked)
        row.addWidget(self._prev_button)

        self._index_label = QLabel("")
        self._index_label.setObjectName("charts_tab.nav.index_label")
        row.addWidget(self._index_label)

        self._next_button = QPushButton(">")
        self._next_button.setObjectName("charts_tab.nav.next")
        self._next_button.setToolTip("Next chart")
        self._next_button.clicked.connect(self.next_clicked)
        row.addWidget(self._next_button)

        self._kind_dropdown = QComboBox()
        self._kind_dropdown.setObjectName("charts_tab.chart_kind_dropdown")
        self._kind_dropdown.currentIndexChanged.connect(self._on_kind_index_changed)
        row.addWidget(self._kind_dropdown)
        row.addStretch()

        self._detach_button = QPushButton("Detach window")
        self._detach_button.setObjectName("charts_tab.detach")
        self._detach_button.setToolTip("Open this chart in its own window")
        self._detach_button.clicked.connect(self.detach_clicked)
        row.addWidget(self._detach_button)
        return row

    def _build_filter_bar(self, *, spacing_px: int) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(spacing_px)
        self._chip_models = _FilterChipButton(object_suffix="models", label="Models")
        self._chip_status = _FilterChipButton(object_suffix="status", label="Status")
        self._chip_verdict = _FilterChipButton(object_suffix="verdict", label="Verdict")
        self._chip_category = _FilterChipButton(object_suffix="category", label="Category")
        self._chip_difficulty = _FilterChipButton(object_suffix="difficulty", label="Difficulty")
        for chip_name, chip in (
            ("models", self._chip_models),
            ("statuses", self._chip_status),
            ("verdicts", self._chip_verdict),
            ("categories", self._chip_category),
            ("difficulties", self._chip_difficulty),
        ):
            chip.selection_changed.connect(partial(self._on_chip_changed, chip_name))
            row.addWidget(chip)
        row.addStretch()
        self._clear_filters_button = QPushButton("Clear filters")
        self._clear_filters_button.setObjectName("charts_tab.clear_filters")
        self._clear_filters_button.clicked.connect(self.clear_filters_clicked)
        row.addWidget(self._clear_filters_button)
        self._options_row = QHBoxLayout()
        row.addLayout(self._options_row)
        return bar

    def apply(self, view_model: ChartsViewModel) -> None:
        """Render the toolbars, filter chips, per-chart options, and canvas."""
        self._apply_nav(view_model)
        self._apply_dropdown(view_model)
        self._apply_chips(view_model)
        self._apply_options(view_model)
        self._meta_line_label.setText(view_model.meta_line)
        self._clear_filters_button.setEnabled(view_model.clear_filters_enabled)
        self._detach_button.setEnabled(view_model.detach_enabled)
        self._canvas.apply(view_model)

    def apply_no_run(self, message: str) -> None:
        """Render the "select a run" state: no chips, an empty canvas message."""
        self._meta_line_label.setText("")
        self._prev_button.setEnabled(False)
        self._next_button.setEnabled(False)
        self._kind_dropdown.clear()
        self._canvas.apply_no_run(message)

    def set_export_enabled(self, *, enabled: bool) -> None:
        """Track the run's terminal-state readiness (the export buttons live on
        the shared footer, not on this view)."""

    def _apply_nav(self, vm: ChartsViewModel) -> None:
        self._prev_button.setEnabled(vm.prev_enabled)
        self._next_button.setEnabled(vm.next_enabled)
        self._index_label.setText(f"{vm.chart_index + 1} / {vm.chart_count}")

    def _apply_dropdown(self, vm: ChartsViewModel) -> None:
        self._kind_dropdown.blockSignals(True)  # noqa: FBT003  # Qt's own blockSignals(bool) API
        try:
            self._kind_dropdown.clear()
            for kind, label, has_data in vm.dropdown_entries:
                text = label if has_data else f"{label}{_NO_DATA_SUFFIX}"
                self._kind_dropdown.addItem(text, userData=kind.value)
            index = self._kind_dropdown.findData(vm.chart_kind.value)
            if index >= 0:
                self._kind_dropdown.setCurrentIndex(index)
        finally:
            self._kind_dropdown.blockSignals(False)  # noqa: FBT003  # Qt's own blockSignals(bool) API

    def _apply_chips(self, vm: ChartsViewModel) -> None:
        domains = vm.filter_domains
        selection = vm.filter_selection
        self._chip_models.set_options(
            tuple(f"{name} / {model}" for _pid, model, name in domains.models),
            checked=tuple(
                f"{name} / {model}"
                for pid, model in selection.models
                for _p, m, name in domains.models
                if (_p, m) == (pid, model)
            ),
        )
        self._chip_status.set_options(domains.statuses, checked=selection.statuses)
        self._chip_verdict.set_options(domains.verdicts, checked=selection.verdicts)
        self._chip_verdict.setVisible(vm.verdict_filter_visible)
        self._chip_category.set_options(domains.categories, checked=selection.categories)
        self._chip_difficulty.set_options(domains.difficulties, checked=selection.difficulties)

    def _apply_options(self, vm: ChartsViewModel) -> None:
        while self._options_row.count():
            item = self._options_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for control in vm.option_controls:
            self._options_row.addWidget(self._build_option_widget(control))

    def _build_option_widget(self, control: ChartOptionControl) -> QWidget:
        if control.kind == "toggle":
            checkbox = QPushButton(control.label)
            checkbox.setCheckable(True)
            checkbox.setChecked(control.value == "true")
            checkbox.toggled.connect(partial(self._on_toggle_changed, control.key))
            return checkbox
        combo = QComboBox()
        combo.setToolTip(control.label)
        for choice in control.choices:
            combo.addItem(choice)
        index = combo.findText(control.value)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.currentTextChanged.connect(partial(self._on_select_changed, control.key))
        return combo

    def _on_toggle_changed(self, key: str, checked: bool) -> None:  # noqa: FBT001  # Qt signal callback
        self.option_changed.emit(key, "true" if checked else "false")

    def _on_select_changed(self, key: str, value: str) -> None:
        self.option_changed.emit(key, value)

    def _on_kind_index_changed(self, index: int) -> None:
        if index < 0:
            return
        value = self._kind_dropdown.itemData(index)
        if value is None:
            return
        self.chart_kind_selected.emit(str(value))

    def _on_chip_changed(self, chip_name: str, values: tuple[str, ...]) -> None:
        self.filter_changed.emit(chip_name, list(values))
