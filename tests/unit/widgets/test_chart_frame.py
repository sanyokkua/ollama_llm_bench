"""Tests for ChartFrame detachable flag, tooltips, and detach-dialog behaviour."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QMargins
from PySide6.QtWidgets import QApplication, QDialog
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.models import BenchmarkResult, BenchmarkRun
from ollama_llm_bench.backend.services.charts.base_chart import (
    BaseChartAggregator,
    ChartData,
    ChartFilters,
    FilterDescriptor,
)
from ollama_llm_bench.ui.widgets.panels.result.charts.chart_frame import ChartFrame

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
# Helper factory
# ---------------------------------------------------------------------------


def _make_frame(qapp: QApplication, *, detachable: bool = True) -> ChartFrame:
    """Construct a minimal ChartFrame with the given detachable flag."""
    return ChartFrame(
        aggregator=_MinimalAggregator(),
        chart_name="Test Chart",
        chart_kind="bar",
        tokens={},
        detachable=detachable,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_detachable_false_hides_detach_button(qapp: QApplication) -> None:
    # Arrange / Act
    frame = _make_frame(qapp, detachable=False)

    # Assert — isHidden() reflects the explicit hide flag, independent of
    # whether the top-level window has been shown.
    assert frame._detach_btn.isHidden()  # type: ignore[attr-defined]


def test_detachable_true_shows_detach_button(qapp: QApplication) -> None:
    # Arrange / Act
    frame = _make_frame(qapp, detachable=True)

    # Assert — button must NOT be explicitly hidden when detachable=True.
    assert not frame._detach_btn.isHidden()  # type: ignore[attr-defined]


def test_detachable_false_export_button_remains_visible(qapp: QApplication) -> None:
    # Arrange / Act
    frame = _make_frame(qapp, detachable=False)

    # Assert — export button is never hidden regardless of the detachable flag.
    assert not frame._export_btn.isHidden()  # type: ignore[attr-defined]


def test_export_tooltip_is_set(qapp: QApplication) -> None:
    # Arrange / Act
    frame = _make_frame(qapp)

    # Assert
    assert frame._export_btn.toolTip() == "Save the chart as a PNG image."  # type: ignore[attr-defined]


def test_detach_tooltip_is_set(qapp: QApplication) -> None:
    # Arrange / Act
    frame = _make_frame(qapp)

    # Assert
    assert frame._detach_btn.toolTip() == "Open this chart in a separate window."  # type: ignore[attr-defined]


def test_on_detach_clicked_creates_frame_with_detachable_false(
    qapp: QApplication,
    mocker: MockerFixture,
) -> None:
    # Arrange
    parent_frame = _make_frame(qapp, detachable=True)
    dialogs_before: set[int] = {id(w) for w in QApplication.topLevelWidgets() if isinstance(w, QDialog)}

    # Act
    parent_frame._on_detach_clicked()  # type: ignore[attr-defined]

    # Assert — find the newly spawned dialog
    new_dialogs = [w for w in QApplication.topLevelWidgets() if isinstance(w, QDialog) and id(w) not in dialogs_before]
    assert len(new_dialogs) == 1, "Expected exactly one new QDialog to appear"
    dialog = new_dialogs[0]

    inner_frames = dialog.findChildren(ChartFrame)
    assert len(inner_frames) == 1, "Expected exactly one inner ChartFrame"
    inner_frame: ChartFrame = inner_frames[0]
    assert inner_frame._detach_btn.isHidden()  # type: ignore[attr-defined]

    dialog.close()


def test_on_detach_clicked_layout_has_12px_margins(
    qapp: QApplication,
    mocker: MockerFixture,
) -> None:
    # Arrange
    parent_frame = _make_frame(qapp, detachable=True)
    dialogs_before: set[int] = {id(w) for w in QApplication.topLevelWidgets() if isinstance(w, QDialog)}

    # Act
    parent_frame._on_detach_clicked()  # type: ignore[attr-defined]

    # Assert — find the newly spawned dialog
    new_dialogs = [w for w in QApplication.topLevelWidgets() if isinstance(w, QDialog) and id(w) not in dialogs_before]
    assert len(new_dialogs) == 1, "Expected exactly one new QDialog to appear"
    dialog = new_dialogs[0]

    layout = dialog.layout()
    assert layout is not None
    assert layout.contentsMargins() == QMargins(12, 12, 12, 12)

    dialog.close()
