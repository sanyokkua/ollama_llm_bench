"""The shared ``ChartAggregator`` contract-test suite — runs against both the real,
stateless aggregator (``make_chart_aggregator()``) and its ``testing.py`` fake
(``FakeChartAggregator``), proving the fake is a faithful stand-in.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md``
"The shared contract-test suite per Protocol"; ``docs/stories/story-033-chart-aggregators.md``
Definition of Done. Mirrors the pattern established by
``tests/contract/test_llm_client_contract.py``: one parametrized fixture over
``["real", "fake"]``, one representative ``compute()`` call per ``ChartKind`` (twelve
total), asserting both implementations return a structurally valid
``ChartData``/``HeatmapData`` — never that both return byte-identical structures,
since the fake's canned empty-state response is not required to match the real
aggregator's computed one.
"""

import pytest

from ollama_llm_bench.backend.charts import ChartAggregator, make_chart_aggregator
from ollama_llm_bench.backend.charts.testing import FakeChartAggregator
from ollama_llm_bench.backend.charts.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)
from ollama_llm_bench.backend.domain import (
    ChartData,
    ChartFilters,
    ChartKind,
    HeatmapData,
    RunMode,
    Verdict,
)

pytestmark = pytest.mark.integration

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME = "model-a"
_GRADING_KINDS = frozenset(
    {
        ChartKind.PASS_RATE_BY_MODEL,
        ChartKind.AVG_COSINE_BY_MODEL,
        ChartKind.VERDICT_COUNTS_STACKED,
        ChartKind.HEATMAP_TASK_BY_MODEL,
        ChartKind.PER_CATEGORY_BAR,
        ChartKind.SPEED_VS_QUALITY_SCATTER,
    }
)


def _run_mode_for(chart_kind: ChartKind) -> RunMode:
    return RunMode.GRADED if chart_kind in _GRADING_KINDS else RunMode.TASKS


@pytest.fixture(params=["real", "fake"])
def chart_aggregator(request: pytest.FixtureRequest) -> ChartAggregator:
    """Parametrized ``ChartAggregator`` under test: the real, stateless
    aggregator and its ``testing.py`` fake — every leg runs every test below."""
    if request.param == "real":
        return make_chart_aggregator()
    return FakeChartAggregator()


def _assert_structurally_valid(result: ChartData | HeatmapData, chart_kind: ChartKind) -> None:
    if chart_kind == ChartKind.HEATMAP_TASK_BY_MODEL:
        assert isinstance(result, HeatmapData)
        assert len(result.cells) == len(result.row_labels)
        assert all(len(cell_row) == len(result.column_labels) for cell_row in result.cells)
        return
    assert isinstance(result, ChartData)
    assert result.chart_kind == chart_kind
    assert isinstance(result.categories, tuple)
    assert isinstance(result.series, tuple)
    assert all(isinstance(series.values, tuple) for series in result.series)


@pytest.mark.parametrize("chart_kind", list(ChartKind), ids=lambda kind: kind.value)
def test_compute_returns_structurally_valid_structure(
    chart_aggregator: ChartAggregator, chart_kind: ChartKind
) -> None:
    """Proves: STORY-033-AC-1

    Given any ``ChartAggregator`` implementation (real or fake), when
    ``compute()`` is called for each of the twelve ``ChartKind`` values,
    then it returns a structurally valid ``ChartData`` (or ``HeatmapData``
    for the heatmap kind) — the Protocol-level return-shape contract both
    legs must honour.
    """
    # Arrange
    task = make_benchmark_task()
    row = make_benchmark_result(
        result_id=1,
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        verdict=Verdict.PASS,
        cosine_similarity=0.9,
    )

    # Act
    result = chart_aggregator.compute(
        chart_kind=chart_kind,
        run_mode=_run_mode_for(chart_kind),
        results=(row,),
        tasks=(task,),
        filters=ChartFilters(),
    )

    # Assert
    _assert_structurally_valid(result, chart_kind)


def test_compute_never_raises_for_an_empty_result_set(chart_aggregator: ChartAggregator) -> None:
    """Proves: STORY-033-AC-8

    Given any ``ChartAggregator`` implementation, when ``compute()`` is
    called with no result rows, then it never raises and returns the
    kind-specific empty-state structure — the never-raises Protocol
    contract holds identically for the real aggregator and the fake.
    """
    # Act
    result = chart_aggregator.compute(
        chart_kind=ChartKind.AVG_TTFT_PER_MODEL,
        run_mode=RunMode.TASKS,
        results=(),
        tasks=(),
        filters=ChartFilters(),
    )

    # Assert
    assert isinstance(result, ChartData)
    assert result.empty_state_message is not None
