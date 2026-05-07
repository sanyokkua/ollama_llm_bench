"""Widget-level tests for ChartFrame._export_png — dimensions, caption, and side-effects."""

from __future__ import annotations

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
    tmp_path,
) -> None:
    # Arrange
    out = str(tmp_path / "out.png")

    # Act
    chart_frame._export_png(out)  # type: ignore[attr-defined]

    # Assert
    image = QImage(out)
    assert not image.isNull()
    assert image.width() == _EXPORT_CHART_W
    assert image.height() == _EXPORT_CHART_H + _EXPORT_CAPTION_H


def test_export_caption_strip_height_is_60px(
    chart_frame: ChartFrame,
    tmp_path,
) -> None:
    # Arrange
    out = str(tmp_path / "out.png")

    # Act
    chart_frame._export_png(out)  # type: ignore[attr-defined]

    # Assert
    image = QImage(out)
    assert image.height() - _EXPORT_CHART_H == _EXPORT_CAPTION_H


def test_export_does_not_change_canvas_size(
    chart_frame: ChartFrame,
    tmp_path,
) -> None:
    # Arrange
    chart_frame.resize(400, 300)
    before = chart_frame._chart_view.size()  # type: ignore[attr-defined]
    out = str(tmp_path / "out.png")

    # Act
    chart_frame._export_png(out)  # type: ignore[attr-defined]

    # Assert
    assert chart_frame._chart_view.size() == before  # type: ignore[attr-defined]


def test_export_emits_exported_signal_on_success(
    chart_frame: ChartFrame,
    mocker: MockerFixture,
    tmp_path,
) -> None:
    # Arrange
    received: list[str] = []
    chart_frame.exported.connect(received.append)
    out = str(tmp_path / "out.png")

    # Act
    chart_frame._export_png(out)  # type: ignore[attr-defined]

    # Assert
    assert received == [out]


def test_export_does_not_emit_exported_signal_on_save_failure(
    chart_frame: ChartFrame,
    mocker: MockerFixture,
    tmp_path,
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
    chart_frame._export_png(out)  # type: ignore[attr-defined]

    # Assert
    assert received == []
