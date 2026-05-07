"""HeatmapWidget — custom QPainter widget for Chart 9 (per-task heatmap)."""

from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.models import BenchmarkResult, BenchmarkRun
from ollama_llm_bench.backend.services.charts.base_chart import (
    BaseChartAggregator,
    ChartFilters,
    HeatmapData,
)

logger = logging.getLogger(__name__)

_EXPORT_CHART_W: int = 2400
_EXPORT_CHART_H: int = 1600
_EXPORT_CAPTION_H: int = 60


class HeatmapWidget(QWidget):
    """Custom QPainter widget rendering a score heatmap grid.

    Each row is a model; each column is a task. Cells are colour-coded from
    red (0.0 / fail) through yellow (0.5) to green (1.0 / pass).
    """

    _CELL_W: int = 60
    _CELL_H: int = 32
    _MARGIN_LEFT: int = 140
    _MARGIN_TOP: int = 4
    _MARGIN_BOTTOM: int = 90

    def __init__(self, *, data: HeatmapData, tokens: dict[str, str]) -> None:
        """Initialise the heatmap widget with grid data and design tokens.

        Args:
            data: Grid data containing row/column labels and cell values.
            tokens: Design token dict mapping token names to hex strings.
        """
        super().__init__()
        self._data: HeatmapData = data
        self._tokens: dict[str, str] = tokens
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        """Return the preferred size based on the grid dimensions.

        Returns:
            QSize wide enough for all columns and tall enough for all rows
            plus top and bottom margins.
        """
        width = self._MARGIN_LEFT + len(self._data.col_labels) * self._CELL_W
        height = len(self._data.row_labels) * self._CELL_H + self._MARGIN_TOP + self._MARGIN_BOTTOM
        return QSize(width, height)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the heatmap grid, model labels, rotated task labels, and cell values.

        Args:
            event: The paint event (unused directly but required by Qt).
        """
        painter = QPainter(self)
        self._draw_heatmap(painter, self.width(), self.height())
        painter.end()

    def _draw_heatmap(self, painter: QPainter, width: int, height: int) -> None:
        """Draw the full heatmap grid onto painter using the given dimensions.

        Args:
            painter: Active QPainter to draw into.
            width: Canvas width in pixels.
            height: Canvas height in pixels.
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_color = QColor(self._tokens.get("bg_card", "#263044"))
        painter.fillRect(QRect(0, 0, width, height), bg_color)

        text_color = QColor(self._tokens.get("text_primary", "#F9FAFB"))
        border_color = QColor(self._tokens.get("border", "#374151"))

        small_font = QFont()
        small_font.setPointSize(9)
        painter.setFont(small_font)
        painter.setPen(text_color)

        for row_idx, model in enumerate(self._data.row_labels):
            y = self._MARGIN_TOP + row_idx * self._CELL_H + self._CELL_H // 2
            label_rect = QRect(0, y - self._CELL_H // 2, self._MARGIN_LEFT - 4, self._CELL_H)
            painter.drawText(label_rect, (0x0001 | 0x0080), model)  # AlignLeft | AlignVCenter

        for col_idx, task in enumerate(self._data.col_labels):
            x = self._MARGIN_LEFT + col_idx * self._CELL_W + self._CELL_W // 2
            y = self._MARGIN_TOP + len(self._data.row_labels) * self._CELL_H + 4
            painter.save()
            painter.translate(x, y)
            painter.rotate(45.0)
            painter.drawText(QRect(0, 0, self._MARGIN_BOTTOM - 8, 20), 0x0001, task)
            painter.restore()

        for row_idx, model in enumerate(self._data.row_labels):
            for col_idx, task in enumerate(self._data.col_labels):
                rect = QRect(
                    self._MARGIN_LEFT + col_idx * self._CELL_W,
                    self._MARGIN_TOP + row_idx * self._CELL_H,
                    self._CELL_W,
                    self._CELL_H,
                )
                value: float | None = self._data.cells.get((model, task))
                cell_color = self._color_for(value)
                painter.fillRect(rect, cell_color)

                painter.setPen(border_color)
                painter.drawRect(rect)

                painter.setPen(text_color)
                cell_text = f"{value:.2f}" if value is not None else "—"
                painter.drawText(rect, (0x0004 | 0x0080), cell_text)  # AlignHCenter | AlignVCenter

    def render_to_image(self, *, width: int, height: int) -> QImage:
        """Render the heatmap to a fixed-size QImage for export.

        Args:
            width: Target image width in pixels.
            height: Target image height in pixels.

        Returns:
            A QImage of the specified dimensions filled with the heatmap content.
        """
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(QColor(self._tokens.get("bg_card", "#263044")))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._draw_heatmap(painter, width, height)
        painter.end()
        return image

    def _color_for(self, value: float | None) -> QColor:
        """Map a score value to a heatmap colour interpolated between failure and success.

        Args:
            value: Score in [0.0, 1.0], or None for missing data.

        Returns:
            QColor representing the score visually.
        """
        if value is None:
            return QColor(self._tokens.get("border", "#374151"))

        clamped = max(0.0, min(1.0, value))

        failure_color = QColor(self._tokens.get("failure", "#F87171"))
        warning_color = QColor(self._tokens.get("warning", "#FBBF24"))
        success_color = QColor(self._tokens.get("success", "#34D399"))

        if clamped <= 0.5:
            t = clamped / 0.5
            r = int(failure_color.red() + t * (warning_color.red() - failure_color.red()))
            g = int(failure_color.green() + t * (warning_color.green() - failure_color.green()))
            b = int(failure_color.blue() + t * (warning_color.blue() - failure_color.blue()))
        else:
            t = (clamped - 0.5) / 0.5
            r = int(warning_color.red() + t * (success_color.red() - warning_color.red()))
            g = int(warning_color.green() + t * (success_color.green() - warning_color.green()))
            b = int(warning_color.blue() + t * (success_color.blue() - warning_color.blue()))

        return QColor(r, g, b)


class HeatmapFrame(QWidget):
    """Scrollable container for HeatmapWidget with a filter row and export button.

    Wraps a HeatmapWidget in a QScrollArea with a sort-by combo, compact-view
    toggle, and export/detach controls.

    Attributes:
        exported: Emitted with the file path after a successful PNG export.
    """

    exported: Signal = Signal(str)

    def __init__(
        self,
        *,
        aggregator: BaseChartAggregator,
        tokens: dict[str, str],
    ) -> None:
        """Initialise the frame with the given aggregator and design tokens.

        Args:
            aggregator: Pure-Python aggregator (expected to be a Chart9
                HeatmapAggregator) that produces ChartData with a heatmap field.
            tokens: Design token dict for colour values.
        """
        super().__init__()
        self._aggregator: BaseChartAggregator = aggregator
        self._tokens: dict[str, str] = tokens
        self._run: BenchmarkRun | None = None
        self._results: list[BenchmarkResult] = []
        self._filter_state: dict[str, object] = {fd.field_id: fd.default for fd in aggregator.required_filters()}
        self._sort_combo: QComboBox = QComboBox()
        self._compact_check: QCheckBox = QCheckBox("Compact")
        self._export_btn: QPushButton = QPushButton("Export PNG")
        self._detach_btn: QPushButton = QPushButton("⤢")
        self._scroll: QScrollArea = QScrollArea()
        self._footnote_label: QLabel = QLabel()
        self._build_ui()

    # ------------------------------------------------------------------
    # Private: UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Build the complete layout: filter row, scroll area, footnote."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(4)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # --- Filter row ---
        filter_row_widget = QWidget()
        filter_layout = QHBoxLayout(filter_row_widget)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(6)

        filter_layout.addWidget(QLabel("Sort by:"))
        self._sort_combo.addItems(["model_name", "avg_score", "pass_rate"])
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        filter_layout.addWidget(self._sort_combo)

        filter_layout.addWidget(self._compact_check)

        filter_layout.addStretch()
        filter_layout.addWidget(self._export_btn)
        filter_layout.addWidget(self._detach_btn)

        main_layout.addWidget(filter_row_widget)

        # --- Scroll area ---
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setWidgetResizable(False)
        main_layout.addWidget(self._scroll, 1)

        # --- Footnote ---
        self._footnote_label.setProperty("role", "secondary")
        self._footnote_label.setVisible(False)
        main_layout.addWidget(self._footnote_label)

        # --- Connections ---
        self._export_btn.clicked.connect(self._on_export_clicked)
        self._detach_btn.clicked.connect(self._on_detach_clicked)
        self._compact_check.stateChanged.connect(self._on_compact_changed)

    # ------------------------------------------------------------------
    # Public: data update
    # ------------------------------------------------------------------

    def update_run_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
    ) -> None:
        """Replace current run and results, rebuild filters, and re-render.

        Args:
            run: The newly selected BenchmarkRun, or None.
            results: All BenchmarkResult rows for that run.
        """
        self._run = run
        self._results = results
        self._rebuild_model_filter(results)
        self._recompute_and_render()

    # ------------------------------------------------------------------
    # Private: filter helpers
    # ------------------------------------------------------------------

    def _rebuild_model_filter(self, results: list[BenchmarkResult]) -> None:
        """Populate model_name frozenset from the current result list.

        Args:
            results: Result rows used to build the available model set.
        """
        for fd in self._aggregator.required_filters():
            if fd.kind == "multi_check" and fd.field_id == "model_name":
                self._filter_state["model_name"] = frozenset(r.model_name for r in results)

    def _build_chart_filters(self) -> ChartFilters:
        """Assemble ChartFilters from the current filter state.

        Returns:
            Immutable ChartFilters for the aggregator call.
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
    # Private: recompute + render
    # ------------------------------------------------------------------

    def _recompute_and_render(self) -> None:
        """Build filters, invoke aggregator, and update the scroll area widget."""
        filters = self._build_chart_filters()
        data = self._aggregator.compute_data(run=self._run, results=self._results, filters=filters)

        if data.footnote:
            self._footnote_label.setText(data.footnote)
            self._footnote_label.setVisible(True)
        else:
            self._footnote_label.setVisible(False)

        if data.heatmap is not None:
            heatmap_widget = HeatmapWidget(data=data.heatmap, tokens=self._tokens)
            self._scroll.setWidget(heatmap_widget)
        else:
            placeholder = QLabel(data.empty_state_message or "No data available")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setProperty("role", "secondary")
            self._scroll.setWidget(placeholder)

    # ------------------------------------------------------------------
    # Private: slot handlers
    # ------------------------------------------------------------------

    def _on_sort_changed(self, _index: int) -> None:
        """Handle sort_by combo change by updating filter state and re-rendering."""
        self._filter_state["sort_by"] = self._sort_combo.currentText()
        self._recompute_and_render()

    def _on_compact_changed(self, state: int) -> None:
        """Handle compact_view checkbox change by updating filter state and re-rendering.

        Args:
            state: Qt check state integer.
        """
        self._filter_state["compact_view"] = bool(state)
        self._recompute_and_render()

    def _on_export_clicked(self) -> None:
        """Open a save-file dialog and export the heatmap as a full-size PNG."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Heatmap",
            "heatmap.png",
            "PNG (*.png)",
        )
        if not path:
            return
        scroll_widget = self._scroll.widget()
        if not isinstance(scroll_widget, HeatmapWidget):
            logger.warning("No heatmap widget to export")
            return

        chart_image = scroll_widget.render_to_image(width=_EXPORT_CHART_W, height=_EXPORT_CHART_H)

        final = QPixmap(_EXPORT_CHART_W, _EXPORT_CHART_H + _EXPORT_CAPTION_H)
        final.fill(QColor(self._tokens.get("bg_card", "#263044")))

        composer = QPainter(final)
        composer.drawImage(0, 0, chart_image)

        caption_rect = QRect(0, _EXPORT_CHART_H, _EXPORT_CHART_W, _EXPORT_CAPTION_H)
        composer.setPen(QColor(self._tokens.get("text_primary", "#F9FAFB")))
        caption_font = QFont()
        caption_font.setPointSize(14)
        composer.setFont(caption_font)
        caption = f"Heatmap · {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        composer.drawText(caption_rect, Qt.AlignmentFlag.AlignCenter, caption)
        composer.end()

        if final.save(path):
            logger.info("Heatmap exported to %s", path)
            self.exported.emit(path)
        else:
            logger.warning("Failed to save heatmap PNG to %s", path)

    def _on_detach_clicked(self) -> None:
        """Open a non-modal dialog containing a fresh HeatmapFrame."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("Heatmap")
        dialog.resize(900, 600)
        dialog.setMinimumSize(600, 400)

        frame = HeatmapFrame(aggregator=self._aggregator, tokens=self._tokens)
        frame.update_run_data(run=self._run, results=self._results)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(frame)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(dialog.close)
        close_button = button_box.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setDefault(True)
        layout.addWidget(button_box)

        dialog.show()
