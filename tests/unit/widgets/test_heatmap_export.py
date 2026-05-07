"""Widget-level tests for HeatmapWidget.render_to_image and HeatmapFrame export."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from ollama_llm_bench.backend.services.charts.base_chart import HeatmapData
from ollama_llm_bench.ui.widgets.panels.result.charts.heatmap_widget import (
    _EXPORT_CHART_H,
    _EXPORT_CHART_W,
    HeatmapWidget,
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
# Minimal heatmap data
# ---------------------------------------------------------------------------


def _minimal_heatmap() -> HeatmapData:
    return HeatmapData(
        row_labels=("model_a",),
        col_labels=("task_1",),
        cells={("model_a", "task_1"): 0.8},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def heatmap_widget(qapp: QApplication) -> HeatmapWidget:
    """Return a HeatmapWidget populated with minimal data."""
    return HeatmapWidget(data=_minimal_heatmap(), tokens={})


# ---------------------------------------------------------------------------
# render_to_image tests
# ---------------------------------------------------------------------------


def test_render_to_image_returns_image_of_requested_dimensions(
    heatmap_widget: HeatmapWidget,
) -> None:
    # Act
    image = heatmap_widget.render_to_image(width=2400, height=1600)

    # Assert
    assert image.width() == 2400
    assert image.height() == 1600


def test_render_to_image_format_is_argb32(
    heatmap_widget: HeatmapWidget,
) -> None:
    # Act
    image = heatmap_widget.render_to_image(width=100, height=100)

    # Assert
    assert image.format() == QImage.Format.Format_ARGB32


def test_render_to_image_returns_non_null_image(
    heatmap_widget: HeatmapWidget,
) -> None:
    # Act
    image = heatmap_widget.render_to_image(width=_EXPORT_CHART_W, height=_EXPORT_CHART_H)

    # Assert
    assert not image.isNull()


def test_heatmap_widget_size_unchanged_after_render_to_image(
    heatmap_widget: HeatmapWidget,
) -> None:
    # Arrange
    heatmap_widget.resize(300, 200)
    before = heatmap_widget.size()

    # Act
    heatmap_widget.render_to_image(width=_EXPORT_CHART_W, height=_EXPORT_CHART_H)

    # Assert
    assert heatmap_widget.size() == before
