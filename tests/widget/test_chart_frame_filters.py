"""Tests for ChartFrame multi_check filter integration."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkRun,
    BenchmarkRunStatus,
    RunMode,
)
from ollama_llm_bench.backend.services.charts.base_chart import (
    BaseChartAggregator,
    ChartData,
    ChartFilters,
    FilterDescriptor,
)
from ollama_llm_bench.ui.widgets.common.multi_check_filter_button import MultiCheckFilterButton
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
# Stubs
# ---------------------------------------------------------------------------


class _ModelFilterAggregator(BaseChartAggregator):
    """Aggregator that declares a single model_name multi_check filter."""

    def required_filters(self) -> tuple[FilterDescriptor, ...]:
        return (
            FilterDescriptor(
                field_id="model_name",
                label="Models",
                kind="multi_check",
                options=(),
                default=frozenset(),
            ),
        )

    def compute_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
        filters: ChartFilters,
    ) -> ChartData:
        matching = [r for r in results if r.model_name in filters.included_models]
        if not matching:
            return ChartData(empty_state_message="No data")
        labels = sorted({r.model_name for r in matching})
        values = [float(len([r for r in matching if r.model_name == lbl])) for lbl in labels]
        return ChartData(
            series_labels=tuple(labels),
            series_data=(tuple(values),),
            category_labels=("count",),
        )


def _make_result(*, model_name: str, task_id: str = "t1") -> BenchmarkResult:
    return BenchmarkResult(
        model_name=model_name,
        task_id=task_id,
        task_category="reasoning",
        status=BenchmarkResultStatus.COMPLETED,
        has_inference_error=False,
        has_judge_error=False,
    )


def _make_run() -> BenchmarkRun:
    return BenchmarkRun(
        run_id=1,
        timestamp="2024-01-01T00:00:00",
        judge_model="judge",
        status=BenchmarkRunStatus.COMPLETED,
        run_mode=RunMode.FULL_GRADING,
    )


def _make_frame(qapp: QApplication) -> ChartFrame:
    return ChartFrame(
        aggregator=_ModelFilterAggregator(),
        chart_name="Test",
        chart_kind="bar",
        tokens={},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_multi_check_buttons_created_for_multi_check_filters(qapp: QApplication) -> None:
    # Arrange / Act
    frame = _make_frame(qapp)

    # Assert
    buttons = frame._multi_check_buttons  # type: ignore[attr-defined]
    assert "model_name" in buttons
    assert isinstance(buttons["model_name"], MultiCheckFilterButton)


def test_filter_state_reset_to_all_on_run_change(qapp: QApplication) -> None:
    # Arrange
    frame = _make_frame(qapp)
    r1 = _make_result(model_name="alpha")
    r2 = _make_result(model_name="beta")
    r3 = _make_result(model_name="gamma")

    # Act — first load with 3 models
    frame.update_run_data(run=None, results=[r1, r2, r3])
    state_first = frame._filter_state.get("model_name")  # type: ignore[attr-defined]

    # Assert — all three models are included
    assert isinstance(state_first, frozenset)
    assert state_first == frozenset({"alpha", "beta", "gamma"})

    # Act — second load with a single model
    r4 = _make_result(model_name="delta")
    frame.update_run_data(run=None, results=[r4])
    state_second = frame._filter_state.get("model_name")  # type: ignore[attr-defined]

    # Assert — only the new model is present
    assert isinstance(state_second, frozenset)
    assert state_second == frozenset({"delta"})


def test_empty_selection_shows_empty_state(qapp: QApplication) -> None:
    # Arrange
    frame = _make_frame(qapp)
    frame.update_run_data(run=None, results=[_make_result(model_name="alpha")])

    # Act — clear the selection and commit via menu close
    btn: MultiCheckFilterButton = frame._multi_check_buttons["model_name"]  # type: ignore[attr-defined]
    btn._clear_all()  # type: ignore[attr-defined]
    btn._on_menu_closed()  # type: ignore[attr-defined]

    # Assert — ChartFrame is showing the empty-state page (index 0), not crashing
    assert frame._stack.currentIndex() == 0  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Note on rendering tests
# ---------------------------------------------------------------------------
# test_chart_renders_after_uncheck_model requires a running QChart with
# QtCharts rendering. The chart canvas state is not easily inspectable in a
# headless unit test (QChart series are rendered to a QPainter scene).
# This path is verified via the manual smoke test described in Brief 11 § Step 6:
#   1. Open the app, load a benchmark run.
#   2. Open a chart tab with a multi_check filter.
#   3. Uncheck one model. Confirm the chart re-renders without the unchecked model.
#   4. Re-check. Confirm the model reappears.
