"""`SPEED_VS_QUALITY_SCATTER`'s Pareto frontier (`13_CHART_AGGREGATORS.md` §7.11)."""

from ollama_llm_bench.backend.charts import make_chart_aggregator
from ollama_llm_bench.backend.charts.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)
from ollama_llm_bench.backend.domain import ChartData, ChartFilters, ChartKind, RunMode, Verdict

_PROVIDER_FAST_GOOD_ID = "11111111-1111-4111-8111-111111111111"
_PROVIDER_SLOW_BAD_ID = "22222222-2222-4222-8222-222222222222"
_PROVIDER_MID_ID = "33333333-3333-4333-8333-333333333333"
_MODEL_FAST_GOOD = "fast-good"
_MODEL_SLOW_BAD = "slow-bad"
_MODEL_MID = "mid"


def test_speed_vs_quality_pareto_frontier() -> None:
    """Proves: STORY-033-AC-7

    Given three models — one fast-and-high-quality, one strictly dominated
    (slower and lower quality than the first on both axes), and one
    middling model dominated by neither of the other two — when
    `SPEED_VS_QUALITY_SCATTER` runs, then the Pareto-frontier list contains
    exactly the non-dominated models, sorted by ascending `x` (§7.11,
    CA-21).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    fast_good_rows = tuple(
        make_benchmark_result(
            result_id=index,
            provider_id=_PROVIDER_FAST_GOOD_ID,
            model_name=_MODEL_FAST_GOOD,
            tokens_per_second=100.0,
            verdict=Verdict.PASS,
        )
        for index in (1, 2)
    )
    slow_bad_rows = tuple(
        make_benchmark_result(
            result_id=index,
            provider_id=_PROVIDER_SLOW_BAD_ID,
            model_name=_MODEL_SLOW_BAD,
            tokens_per_second=10.0,
            verdict=Verdict.FAIL,
        )
        for index in (3, 4)
    )
    # Faster than fast-good but lower pass rate: dominated on neither axis
    # by fast-good (lower y), nor by slow-bad (lower x) — stays on the
    # frontier alongside fast-good.
    mid_rows = (
        make_benchmark_result(
            result_id=5,
            provider_id=_PROVIDER_MID_ID,
            model_name=_MODEL_MID,
            tokens_per_second=150.0,
            verdict=Verdict.FAIL,
        ),
        make_benchmark_result(
            result_id=6,
            provider_id=_PROVIDER_MID_ID,
            model_name=_MODEL_MID,
            tokens_per_second=150.0,
            verdict=Verdict.PASS,
        ),
    )
    rows = fast_good_rows + slow_bad_rows + mid_rows

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.SPEED_VS_QUALITY_SCATTER,
        run_mode=RunMode.GRADED,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(),
    )

    # Assert
    assert isinstance(result, ChartData)
    assert result.pareto_points == ((100.0, 1.0), (150.0, 0.5))


def test_speed_vs_quality_scatter_with_one_model_is_empty_state() -> None:
    """Proves: STORY-033-AC-7

    Given only one model with a completed verdict, when
    `SPEED_VS_QUALITY_SCATTER` runs, then it returns the two-models
    empty-state structure rather than a one-point frontier (§7.11, CA-22).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = (
        make_benchmark_result(
            result_id=1,
            provider_id=_PROVIDER_FAST_GOOD_ID,
            model_name=_MODEL_FAST_GOOD,
            tokens_per_second=100.0,
            verdict=Verdict.PASS,
        ),
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.SPEED_VS_QUALITY_SCATTER,
        run_mode=RunMode.GRADED,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(),
    )

    # Assert
    assert isinstance(result, ChartData)
    assert not result.series
    assert result.empty_state_message == (
        "Speed vs quality needs at least two models with completed verdicts."
    )
