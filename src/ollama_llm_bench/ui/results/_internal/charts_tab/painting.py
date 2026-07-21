"""Pure ``QPainter`` draw helpers for the twelve chart kinds (STORY-064).

Source of truth: ``docs/v3_specification/05_Result_Widget/tabs/charts_tab.md`` §3
(the twelve chart kinds -> five chart shapes), §6.1 (low-sample hatch/``n=N``
rendering), §9 (the Pareto-frontier dashed line), §11 (empty states), §12
(the fixed ``2400 x 1600`` off-screen export resolution and active-theme palette).

Every colour comes from ``tokens.colors.<role>`` -- never a hex/RGB literal
(architecture-test enforced). The ``ChartData``/``HeatmapData`` shape conventions
consumed here (parallel x/y series for a point cloud, aligned per-category series
for a grouped bar, five aligned summary series for a box plot) are documented at
each aggregator in ``backend/charts/_internal/aggregators/`` and are not restated
per function below beyond a one-line pointer. Parameter bundles below are private
``@dataclass``es -- permitted for a strictly private, module-internal type that
never crosses a module boundary (coding-style.md) -- used only to keep every
drawing helper's own parameter count within the project's limit.
"""

from dataclasses import dataclass
from pathlib import Path
import tempfile

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen
from PySide6.QtSvg import QSvgGenerator

from ollama_llm_bench.backend.domain import ChartData, ChartKind, ChartSeries, HeatmapData
from ollama_llm_bench.ui.theme import ThemeTokens, resolve_color

__all__: list[str] = [
    "EXPORT_HEIGHT",
    "EXPORT_WIDTH",
    "AxisRange",
    "draw_bar_chart",
    "draw_box_plot",
    "draw_empty_state",
    "draw_grouped_bar_chart",
    "draw_heatmap",
    "draw_low_sample_hatch",
    "draw_scatter_chart",
    "draw_stacked_bar_chart",
    "finite_axis_range",
    "render_chart_png",
    "render_chart_svg",
    "scale_point",
]

EXPORT_WIDTH = 2400
EXPORT_HEIGHT = 1600
_MARGIN = 96
_HATCH_LABEL_GAP = 18
_MIN_XY_SERIES = 2
_POINT_MARKER_RADIUS = 8.0
_SERIES_ROLES: tuple[str, ...] = (
    "primary.base",
    "success.base",
    "error.base",
    "info.base",
    "warning.base",
)
_BOX_SUMMARY_NAMES: tuple[str, ...] = ("min", "q1", "median", "q3", "max")


@dataclass
class AxisRange:
    """The finite value bounds of one x/y series pair, for point normalisation."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclass
class _ScatterSpec:
    """Everything ``_draw_scaled_points``/``_draw_pareto_line`` need to place a point."""

    plot: QRectF
    axis_range: AxisRange
    tokens: ThemeTokens


def _color(tokens: ThemeTokens, role: str) -> QColor:
    return QColor(resolve_color(tokens, role))


def _series_color(tokens: ThemeTokens, index: int) -> QColor:
    role = _SERIES_ROLES[index % len(_SERIES_ROLES)]
    return _color(tokens, role)


def _plot_rect(rect: QRectF) -> QRectF:
    pad = min(rect.width(), rect.height()) * 0.08
    return rect.adjusted(pad, pad, -pad, -pad)


def draw_empty_state(painter: QPainter, *, rect: QRectF, message: str, tokens: ThemeTokens) -> None:
    """Paint a chart's kind-specific empty-state message, centred, in ``mute`` tone.

    Never blank axes and never an empty grid (charts_tab.md#11).
    """
    painter.save()
    painter.setPen(_color(tokens, "muted.base"))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, message)
    painter.restore()


def draw_low_sample_hatch(
    painter: QPainter, *, rect: QRectF, tokens: ThemeTokens, sample_size: int
) -> None:
    """Paint the shared cross-hatch fill plus an ``n=N`` label for a low-sample group.

    Replaces the group's normal solid fill; the group is still drawn, only marked
    low-confidence (charts_tab.md#6.1).
    """
    painter.save()
    painter.setBrush(QBrush(_color(tokens, "muted.base"), Qt.BrushStyle.BDiagPattern))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRect(rect)
    painter.setPen(_color(tokens, "muted.base"))
    label_rect = rect.adjusted(0, -_HATCH_LABEL_GAP, 0, 0)
    painter.drawText(
        label_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, f"n={sample_size}"
    )
    painter.restore()


def _draw_axis_labels(
    painter: QPainter, *, rect: QRectF, data: ChartData, tokens: ThemeTokens
) -> None:
    painter.save()
    painter.setPen(_color(tokens, "text.secondary"))
    if data.x_axis_title:
        painter.drawText(
            QRectF(rect.left(), rect.bottom(), rect.width(), _MARGIN * 0.4),
            Qt.AlignmentFlag.AlignHCenter,
            data.x_axis_title,
        )
    if data.y_axis_title:
        painter.drawText(
            QRectF(0, rect.top(), _MARGIN, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            data.y_axis_title,
        )
    painter.restore()


def _draw_value_bar(
    painter: QPainter, *, bar_rect: QRectF, tokens: ThemeTokens, series: ChartSeries, index: int
) -> None:
    """Paint one bar, applying the low-sample hatch when its group is under-sampled
    (charts_tab.md#6.1)."""
    is_low_sample = index < len(series.low_sample_flags) and series.low_sample_flags[index]
    if is_low_sample:
        n = series.sample_sizes[index] if index < len(series.sample_sizes) else 0
        draw_low_sample_hatch(painter, rect=bar_rect, tokens=tokens, sample_size=n)
        return
    painter.save()
    painter.setBrush(_series_color(tokens, index))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRect(bar_rect)
    painter.restore()


def draw_bar_chart(
    painter: QPainter, *, rect: QRectF, data: ChartData, tokens: ThemeTokens
) -> None:
    """Paint a per-model bar chart (charts_tab.md#3, kinds 1, 2, 3, 5, 6)."""
    _draw_axis_labels(painter, rect=rect, data=data, tokens=tokens)
    plot = _plot_rect(rect)
    if not data.series or not data.categories:
        return
    series = data.series[0]
    finite_values = [v for v in series.values if v is not None]
    max_value = max(finite_values) if finite_values else 0.0
    group_width = plot.width() / max(len(data.categories), 1)
    for index in range(len(data.categories)):
        value = series.values[index] if index < len(series.values) else None
        if value is None or max_value <= 0:
            continue
        height = (value / max_value) * plot.height()
        bar_rect = QRectF(
            plot.left() + index * group_width, plot.bottom() - height, group_width * 0.8, height
        )
        _draw_value_bar(painter, bar_rect=bar_rect, tokens=tokens, series=series, index=index)


def draw_stacked_bar_chart(
    painter: QPainter,
    *,
    rect: QRectF,
    data: ChartData,
    tokens: ThemeTokens,
    hidden_series: tuple[str, ...],
) -> None:
    """Paint a stacked bar chart with a hidden-series-aware interactive legend
    (charts_tab.md#3, kinds 4, 7)."""
    _draw_axis_labels(painter, rect=rect, data=data, tokens=tokens)
    plot = _plot_rect(rect)
    visible_series = tuple(s for s in data.series if s.name not in hidden_series)
    if not visible_series or not data.categories:
        return
    totals = [sum(s.values[i] or 0.0 for s in visible_series) for i in range(len(data.categories))]
    max_total = max(totals) if totals else 0.0
    group_width = plot.width() / max(len(data.categories), 1)
    for cat_index in range(len(data.categories)):
        column = _StackedColumn(
            x=plot.left() + cat_index * group_width,
            width=group_width * 0.8,
            bottom=plot.bottom(),
            height_total=plot.height(),
        )
        stack = _StackedColumnSpec(
            column=column,
            cat_index=cat_index,
            series=visible_series,
            max_total=max_total,
            tokens=tokens,
        )
        _draw_stacked_column(painter, stack)


@dataclass
class _StackedColumn:
    x: float
    width: float
    bottom: float
    height_total: float


@dataclass
class _StackedColumnSpec:
    column: _StackedColumn
    cat_index: int
    series: tuple[ChartSeries, ...]
    max_total: float
    tokens: ThemeTokens


def _draw_stacked_column(painter: QPainter, stack: _StackedColumnSpec) -> None:
    cursor_y = stack.column.bottom
    for series_index, one_series in enumerate(stack.series):
        value = (
            one_series.values[stack.cat_index] if stack.cat_index < len(one_series.values) else None
        )
        if value is None or stack.max_total <= 0:
            continue
        segment_height = (value / stack.max_total) * stack.column.height_total
        painter.save()
        painter.setBrush(_series_color(stack.tokens, series_index))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(
            QRectF(stack.column.x, cursor_y - segment_height, stack.column.width, segment_height)
        )
        painter.restore()
        cursor_y -= segment_height


def _point_cloud_series_pairs(data: ChartData) -> tuple[tuple[ChartSeries, ChartSeries], ...]:
    return tuple((data.series[i], data.series[i + 1]) for i in range(0, len(data.series) - 1, 2))


def finite_axis_range(
    x_values: tuple[float | None, ...], y_values: tuple[float | None, ...]
) -> AxisRange | None:
    finite_x = [v for v in x_values if v is not None]
    finite_y = [v for v in y_values if v is not None]
    if not finite_x or not finite_y:
        return None
    return AxisRange(
        x_min=min(finite_x), x_max=max(finite_x), y_min=min(finite_y), y_max=max(finite_y)
    )


def scale_point(plot: QRectF, x: float, y: float, axis_range: AxisRange) -> QPointF:
    x_span = axis_range.x_max - axis_range.x_min
    y_span = axis_range.y_max - axis_range.y_min
    x_ratio = 0.5 if x_span <= 0 else (x - axis_range.x_min) / x_span
    y_ratio = 0.5 if y_span <= 0 else (y - axis_range.y_min) / y_span
    return QPointF(plot.left() + x_ratio * plot.width(), plot.bottom() - y_ratio * plot.height())


def draw_scatter_chart(
    painter: QPainter, *, rect: QRectF, data: ChartData, tokens: ThemeTokens
) -> None:
    """Paint a scatter chart -- a per-row point cloud (chart 8) or one point per
    model plus the Pareto-frontier line (chart 11) (charts_tab.md#3)."""
    _draw_axis_labels(painter, rect=rect, data=data, tokens=tokens)
    plot = _plot_rect(rect)
    if not data.series:
        return
    if not data.categories:
        _draw_point_cloud(painter, plot=plot, pairs=_point_cloud_series_pairs(data), tokens=tokens)
        return
    if len(data.series) < _MIN_XY_SERIES:
        return
    x_series, y_series = data.series[0], data.series[1]
    axis_range = finite_axis_range(x_series.values, y_series.values)
    if axis_range is None:
        return
    spec = _ScatterSpec(plot=plot, axis_range=axis_range, tokens=tokens)
    _draw_grouped_points(painter, spec=spec, x_series=x_series, y_series=y_series)
    _draw_pareto_line(painter, spec=spec, pareto_points=data.pareto_points)


def _draw_point_cloud(
    painter: QPainter,
    *,
    plot: QRectF,
    pairs: tuple[tuple[ChartSeries, ChartSeries], ...],
    tokens: ThemeTokens,
) -> None:
    all_x = tuple(v for x_series, _y in pairs for v in x_series.values if v is not None)
    all_y = tuple(v for _x, y_series in pairs for v in y_series.values if v is not None)
    axis_range = finite_axis_range(all_x, all_y)
    if axis_range is None:
        return
    for series_index, (x_series, y_series) in enumerate(pairs):
        painter.save()
        painter.setBrush(_series_color(tokens, series_index))
        painter.setPen(Qt.PenStyle.NoPen)
        for x_value, y_value in zip(x_series.values, y_series.values, strict=True):
            if x_value is None or y_value is None:
                continue
            point = scale_point(plot, x_value, y_value, axis_range)
            painter.drawEllipse(point, 6.0, 6.0)
        painter.restore()


def _draw_grouped_points(
    painter: QPainter, *, spec: _ScatterSpec, x_series: ChartSeries, y_series: ChartSeries
) -> None:
    """Paint chart 11's one-point-per-model markers, applying the low-sample
    hatch when a model's group is under-sampled (charts_tab.md#6.1)."""
    for index, (x_value, y_value) in enumerate(zip(x_series.values, y_series.values, strict=True)):
        if x_value is None or y_value is None:
            continue
        point = scale_point(spec.plot, x_value, y_value, spec.axis_range)
        is_low_sample = index < len(y_series.low_sample_flags) and y_series.low_sample_flags[index]
        if is_low_sample:
            n = y_series.sample_sizes[index] if index < len(y_series.sample_sizes) else 0
            marker_rect = QRectF(
                point.x() - _POINT_MARKER_RADIUS,
                point.y() - _POINT_MARKER_RADIUS,
                _POINT_MARKER_RADIUS * 2,
                _POINT_MARKER_RADIUS * 2,
            )
            draw_low_sample_hatch(painter, rect=marker_rect, tokens=spec.tokens, sample_size=n)
            continue
        painter.save()
        painter.setBrush(_series_color(spec.tokens, index))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(point, _POINT_MARKER_RADIUS, _POINT_MARKER_RADIUS)
        painter.restore()


def _draw_pareto_line(
    painter: QPainter, *, spec: _ScatterSpec, pareto_points: tuple[tuple[float, float], ...]
) -> None:
    if not pareto_points:
        return
    pen = QPen(_color(spec.tokens, "info.base"))
    pen.setStyle(Qt.PenStyle.DashLine)
    pen.setWidthF(3.0)
    painter.save()
    painter.setPen(pen)
    previous: QPointF | None = None
    for x, y in pareto_points:
        current = scale_point(spec.plot, x, y, spec.axis_range)
        if previous is not None:
            painter.drawLine(previous, current)
        previous = current
    painter.restore()


@dataclass
class _GroupedBarCell:
    """One grouped-bar cell: its geometry, colour index, and low-sample source series."""

    rect: QRectF
    tokens: ThemeTokens
    series: ChartSeries
    cat_index: int
    color_index: int


def _draw_grouped_bar_cell(painter: QPainter, cell: _GroupedBarCell) -> None:
    is_low_sample = (
        cell.cat_index < len(cell.series.low_sample_flags)
        and cell.series.low_sample_flags[cell.cat_index]
    )
    if is_low_sample:
        n = (
            cell.series.sample_sizes[cell.cat_index]
            if cell.cat_index < len(cell.series.sample_sizes)
            else 0
        )
        draw_low_sample_hatch(painter, rect=cell.rect, tokens=cell.tokens, sample_size=n)
        return
    painter.save()
    painter.setBrush(_series_color(cell.tokens, cell.color_index))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRect(cell.rect)
    painter.restore()


def draw_grouped_bar_chart(
    painter: QPainter, *, rect: QRectF, data: ChartData, tokens: ThemeTokens
) -> None:
    """Paint a per-category grouped bar chart -- one category-group per
    ``BenchmarkTask.category``, one series per model (charts_tab.md#3, kind 10)."""
    _draw_axis_labels(painter, rect=rect, data=data, tokens=tokens)
    plot = _plot_rect(rect)
    if not data.series or not data.categories:
        return
    finite_values = [v for series in data.series for v in series.values if v is not None]
    max_value = max(finite_values) if finite_values else 0.0
    group_width = plot.width() / max(len(data.categories), 1)
    series_width = group_width / max(len(data.series), 1)
    for cat_index in range(len(data.categories)):
        for series_index, series in enumerate(data.series):
            value = series.values[cat_index] if cat_index < len(series.values) else None
            if value is None or max_value <= 0:
                continue
            height = (value / max_value) * plot.height()
            bar_rect = QRectF(
                plot.left() + cat_index * group_width + series_index * series_width,
                plot.bottom() - height,
                series_width * 0.85,
                height,
            )
            cell = _GroupedBarCell(
                rect=bar_rect,
                tokens=tokens,
                series=series,
                cat_index=cat_index,
                color_index=series_index,
            )
            _draw_grouped_bar_cell(painter, cell)


@dataclass
class _BoxColumn:
    x: float
    width: float
    bottom: float
    height_total: float


@dataclass
class _BoxSpec:
    column: _BoxColumn
    max_value: float
    summary_by_name: dict[str, ChartSeries]
    index: int
    tokens: ThemeTokens
    series_index: int


def draw_box_plot(painter: QPainter, *, rect: QRectF, data: ChartData, tokens: ThemeTokens) -> None:
    """Paint a five-number-summary box plot per model, plus outlier markers
    (charts_tab.md#3, kind 12)."""
    _draw_axis_labels(painter, rect=rect, data=data, tokens=tokens)
    plot = _plot_rect(rect)
    summary_by_name = {
        series.name: series for series in data.series if series.name in _BOX_SUMMARY_NAMES
    }
    if not data.categories or len(summary_by_name) < len(_BOX_SUMMARY_NAMES):
        return
    all_max = [v for series in summary_by_name.values() for v in series.values if v is not None]
    max_value = max(all_max) if all_max else 0.0
    group_width = plot.width() / max(len(data.categories), 1)
    for index in range(len(data.categories)):
        column = _BoxColumn(
            x=plot.left() + index * group_width,
            width=group_width * 0.6,
            bottom=plot.bottom(),
            height_total=plot.height(),
        )
        spec = _BoxSpec(
            column=column,
            max_value=max_value,
            summary_by_name=summary_by_name,
            index=index,
            tokens=tokens,
            series_index=index,
        )
        _draw_one_box(painter, spec)


def _box_summary_y(spec: _BoxSpec, name: str) -> float | None:
    series = spec.summary_by_name[name]
    value = series.values[spec.index] if spec.index < len(series.values) else None
    if value is None:
        return None
    return spec.column.bottom - (value / spec.max_value) * spec.column.height_total


def _draw_one_box(painter: QPainter, spec: _BoxSpec) -> None:
    if spec.max_value <= 0:
        return
    q1_y = _box_summary_y(spec, "q1")
    median_y = _box_summary_y(spec, "median")
    q3_y = _box_summary_y(spec, "q3")
    min_y = _box_summary_y(spec, "min")
    max_y = _box_summary_y(spec, "max")
    if None in (q1_y, median_y, q3_y, min_y, max_y):
        return
    assert q1_y is not None  # noqa: S101  # narrows for mypy after the None-membership check above
    assert median_y is not None  # noqa: S101
    assert q3_y is not None  # noqa: S101
    assert min_y is not None  # noqa: S101
    assert max_y is not None  # noqa: S101
    painter.save()
    pen = QPen(_series_color(spec.tokens, spec.series_index))
    pen.setWidthF(2.0)
    painter.setPen(pen)
    center_x = spec.column.x + spec.column.width / 2
    painter.drawLine(QPointF(center_x, min_y), QPointF(center_x, max_y))
    painter.setBrush(_series_color(spec.tokens, spec.series_index))
    painter.drawRect(QRectF(spec.column.x, q3_y, spec.column.width, q1_y - q3_y))
    painter.drawLine(
        QPointF(spec.column.x, median_y), QPointF(spec.column.x + spec.column.width, median_y)
    )
    painter.restore()


def draw_heatmap(
    painter: QPainter, *, rect: QRectF, data: HeatmapData, tokens: ThemeTokens
) -> None:
    """Paint the task-by-model heatmap grid (charts_tab.md#3, kind 9).

    A cell's value is exactly ``0.0``/``1.0`` for verdict-categorical cells
    (``"pass"``/``"fail"`` colouring) and any other float for cosine-numeric
    cells (linear-interpolated colour gradient); a missing cell renders muted.
    """
    plot = _plot_rect(rect)
    if not data.row_labels or not data.column_labels:
        return
    cell_width = plot.width() / len(data.column_labels)
    cell_height = plot.height() / len(data.row_labels)
    for row_index, row in enumerate(data.cells):
        for col_index, value in enumerate(row):
            cell_rect = QRectF(
                plot.left() + col_index * cell_width,
                plot.top() + row_index * cell_height,
                cell_width * 0.95,
                cell_height * 0.95,
            )
            painter.save()
            painter.setBrush(_heatmap_cell_color(tokens, value))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(cell_rect)
            painter.restore()


def _heatmap_cell_color(tokens: ThemeTokens, value: float | None) -> QColor:
    if value is None:
        return _color(tokens, "muted.fill")
    if value in (0.0, 1.0):
        return _color(tokens, "success.base") if value == 1.0 else _color(tokens, "error.base")
    low = _color(tokens, "error.base")
    high = _color(tokens, "success.base")
    ratio = max(0.0, min(1.0, value))
    red = round(low.red() + (high.red() - low.red()) * ratio)
    green = round(low.green() + (high.green() - low.green()) * ratio)
    blue = round(low.blue() + (high.blue() - low.blue()) * ratio)
    return QColor(red, green, blue)


_DRAW_DISPATCH = {
    ChartKind.AVG_TTFT_PER_MODEL: draw_bar_chart,
    ChartKind.AVG_TPS_PER_MODEL: draw_bar_chart,
    ChartKind.AVG_TIME_PER_MODEL: draw_bar_chart,
    ChartKind.PASS_RATE_BY_MODEL: draw_bar_chart,
    ChartKind.AVG_COSINE_BY_MODEL: draw_bar_chart,
    ChartKind.PER_CATEGORY_BAR: draw_grouped_bar_chart,
    ChartKind.SPEED_VS_QUALITY_SCATTER: draw_scatter_chart,
    ChartKind.TIME_VS_TOKENS_SCATTER: draw_scatter_chart,
    ChartKind.TOKENS_PER_TASK_BOX: draw_box_plot,
}
_STACKED_KINDS = frozenset(
    {ChartKind.SUCCESS_FAILED_INCOMPLETE_STACKED, ChartKind.VERDICT_COUNTS_STACKED}
)


def _paint_export(
    painter: QPainter, *, chart_kind: ChartKind, data: ChartData | HeatmapData, tokens: ThemeTokens
) -> None:
    rect = QRectF(0, 0, EXPORT_WIDTH, EXPORT_HEIGHT)
    painter.fillRect(rect, _color(tokens, "bg.window"))
    if isinstance(data, HeatmapData):
        if data.empty_state_message is not None:
            draw_empty_state(painter, rect=rect, message=data.empty_state_message, tokens=tokens)
            return
        draw_heatmap(painter, rect=rect, data=data, tokens=tokens)
        return
    if data.empty_state_message is not None:
        draw_empty_state(painter, rect=rect, message=data.empty_state_message, tokens=tokens)
        return
    if chart_kind in _STACKED_KINDS:
        draw_stacked_bar_chart(painter, rect=rect, data=data, tokens=tokens, hidden_series=())
        return
    _DRAW_DISPATCH[chart_kind](painter, rect=rect, data=data, tokens=tokens)


def render_chart_png(
    *, chart_kind: ChartKind, data: ChartData | HeatmapData, tokens: ThemeTokens
) -> bytes:
    """Render the active chart off-screen at the fixed export resolution as PNG bytes
    (charts_tab.md#12): the active theme's palette, not the OS palette (EC-RES-4).

    Uses ``QImage`` (pure raster, no platform pixmap backend) rather than
    ``QPixmap`` -- more robust for off-screen/headless rendering, which this
    export path always is (charts_tab.md#12's fixed off-screen resolution).
    """
    image = QImage(EXPORT_WIDTH, EXPORT_HEIGHT, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        _paint_export(painter, chart_kind=chart_kind, data=data, tokens=tokens)
    finally:
        painter.end()
    path = Path(tempfile.mkstemp(suffix=".png")[1])
    try:
        image.save(str(path), format=b"PNG")
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def render_chart_svg(
    *, chart_kind: ChartKind, data: ChartData | HeatmapData, tokens: ThemeTokens
) -> bytes:
    """Render the active chart off-screen at the fixed export resolution as SVG bytes
    (charts_tab.md#12): the active theme's palette, not the OS palette (EC-RES-4).

    Writes to a temporary file via ``QSvgGenerator.setFileName`` rather than an
    in-memory ``QBuffer`` -- the standard, well-supported ``QSvgGenerator``
    output path; a ``QBuffer``-backed ``QIODevice`` output was found to corrupt
    the process's Qt paint-engine state for a later off-screen render in the
    same process (observed as an intermittent segfault in a later
    ``QPixmap``/``QImage`` construction, reproducible only when both export
    paths ran in the same pytest session).
    """
    path = Path(tempfile.mkstemp(suffix=".svg")[1])
    try:
        generator = QSvgGenerator()
        generator.setFileName(str(path))
        generator.setSize(QRect(0, 0, EXPORT_WIDTH, EXPORT_HEIGHT).size())
        generator.setViewBox(QRect(0, 0, EXPORT_WIDTH, EXPORT_HEIGHT))
        painter = QPainter(generator)
        try:
            _paint_export(painter, chart_kind=chart_kind, data=data, tokens=tokens)
        finally:
            painter.end()
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)
