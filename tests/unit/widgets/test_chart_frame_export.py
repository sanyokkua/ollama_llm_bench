"""Widget-level tests for ChartFrame._export_png — dimensions, caption, and side-effects."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.models import BenchmarkResult, BenchmarkRun
from ollama_llm_bench.backend.services.charts.base_chart import (
    BaseChartAggregator,
    ChartData,
    ChartFilters,
    FilterDescriptor,
)
from ollama_llm_bench.ui.widgets.panels.result.charts.chart_frame import (
    _EXPORT_CAPTION_H,
    _EXPORT_CHART_H,
    _EXPORT_CHART_W,
    ChartFrame,
)

# ---------------------------------------------------------------------------
# QApplication — module scope
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return (or create) a QApplication instance for the module."""
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


# ---------------------------------------------------------------------------
# Minimal aggregator stub
# ---------------------------------------------------------------------------


class _MinimalAggregator(BaseChartAggregator):
    def required_filters(self) -> tuple[FilterDescriptor, ...]:
        return ()

    def compute_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
        filters: ChartFilters,
    ) -> ChartData:
        return ChartData(empty_state_message="No data")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def chart_frame(qapp: QApplication) -> ChartFrame:
    """Return a minimal ChartFrame with a stub aggregator."""
    return ChartFrame(
        aggregator=_MinimalAggregator(),
        chart_name="Test Chart",
        chart_kind="bar",
        tokens={},
    )


# ---------------------------------------------------------------------------
# Export dimension tests
# ---------------------------------------------------------------------------


def test_export_pixmap_dimensions_match_configuration(
    chart_frame: ChartFrame,
    tmp_path: Path,
) -> None:
    # Arrange
    out = str(tmp_path / "out.png")

    # Act
    chart_frame._export_png(out)

    # Assert: width is always the configured export width; height is aspect-preserving
    image = QImage(out)
    assert not image.isNull()
    assert image.width() == _EXPORT_CHART_W
    # Height is at least the caption strip; exact value depends on viewport aspect ratio
    assert image.height() >= _EXPORT_CAPTION_H


def test_export_caption_strip_height_is_60px(
    chart_frame: ChartFrame,
    tmp_path: Path,
) -> None:
    # Arrange: resize viewport to a known aspect ratio
    chart_frame.resize(400, 300)
    out = str(tmp_path / "out.png")

    # Act
    chart_frame._export_png(out)

    # Assert: last _EXPORT_CAPTION_H rows are the caption band
    # Total height = aspect-preserving chart height + caption strip
    image = QImage(out)
    viewport = chart_frame._chart_view.viewport()
    native_w, native_h = viewport.width(), viewport.height()
    expected_chart_h = int(_EXPORT_CHART_W * native_h / native_w) if native_w > 0 else _EXPORT_CHART_H
    assert image.height() == expected_chart_h + _EXPORT_CAPTION_H


def test_export_does_not_change_canvas_size(
    chart_frame: ChartFrame,
    tmp_path: Path,
) -> None:
    # Arrange
    chart_frame.resize(400, 300)
    before = chart_frame._chart_view.size()
    out = str(tmp_path / "out.png")

    # Act
    chart_frame._export_png(out)

    # Assert
    assert chart_frame._chart_view.size() == before


def test_export_emits_exported_signal_on_success(
    chart_frame: ChartFrame,
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    # Arrange
    received: list[str] = []
    chart_frame.exported.connect(received.append)
    out = str(tmp_path / "out.png")

    # Act
    chart_frame._export_png(out)

    # Assert
    assert received == [out]


def test_export_does_not_emit_exported_signal_on_save_failure(
    chart_frame: ChartFrame,
    mocker: MockerFixture,
    tmp_path: Path,
) -> None:
    # Arrange
    mocker.patch(
        "ollama_llm_bench.ui.widgets.panels.result.charts.chart_frame.QPixmap.save",
        return_value=False,
    )
    received: list[str] = []
    chart_frame.exported.connect(received.append)
    out = str(tmp_path / "out.png")

    # Act
    chart_frame._export_png(out)

    # Assert
    assert received == []
