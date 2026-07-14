"""Fixture-based snapshot tests, one per `ChartKind` (`13_CHART_AGGREGATORS.md` §7)."""

from ollama_llm_bench.backend.charts import make_chart_aggregator
from ollama_llm_bench.backend.charts.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)
from ollama_llm_bench.backend.domain import (
    ChartData,
    ChartFilters,
    ChartKind,
    ChartSeries,
    HeatmapData,
    ResultStatus,
    RunMode,
    Verdict,
)

_PROVIDER_A_ID = "11111111-1111-4111-8111-111111111111"
_PROVIDER_B_ID = "22222222-2222-4222-8222-222222222222"
_PROVIDER_A_NAME = "Provider A"
_PROVIDER_B_NAME = "Provider B"
_MODEL_A = "model-a"
_MODEL_B = "model-b"
_LABEL_A = f"{_PROVIDER_A_NAME} / {_MODEL_A}"
_LABEL_B = f"{_PROVIDER_B_NAME} / {_MODEL_B}"


def test_avg_ttft_per_model_matches_fixture() -> None:
    """Proves: STORY-033-AC-1

    Given completed rows with non-null `ttft_ms` for two models, when
    `AVG_TTFT_PER_MODEL` is computed, then the resulting `ChartData` matches
    the §7.1 catalog computation exactly — one bar per model, the mean
    `ttft_ms` in `ms`, with `n`/`low_sample` per group (CA-1).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = (
        make_benchmark_result(
            result_id=1,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            ttft_ms=100,
        ),
        make_benchmark_result(
            result_id=2,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            ttft_ms=200,
        ),
        make_benchmark_result(
            result_id=3,
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            ttft_ms=300,
        ),
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.AVG_TTFT_PER_MODEL,
        run_mode=RunMode.TASKS,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(),
    )

    # Assert
    assert result == ChartData(
        chart_kind=ChartKind.AVG_TTFT_PER_MODEL,
        categories=(_LABEL_A, _LABEL_B),
        series=(
            ChartSeries(
                name="Avg TTFT",
                values=(150.0, 300.0),
                sample_sizes=(2, 1),
                low_sample_flags=(True, True),
            ),
        ),
        x_axis_title="Model",
        y_axis_title="Time to first token",
        value_unit="ms",
    )


def test_avg_tps_per_model_matches_fixture() -> None:
    """Proves: STORY-033-AC-1

    Given completed rows with non-null `tokens_per_second` for two models,
    when `AVG_TPS_PER_MODEL` is computed with the default `mean` aggregation,
    then the resulting `ChartData` matches the §7.2 catalog computation
    exactly, including a per-model `estimated_flags`/`reasoning_flags` pair
    (both `False` here — no fixture row is `tokens_estimated` or
    `has_thinking_block`) (CA-4's median case is covered separately by the
    outlier test).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    model_a_rows = tuple(
        make_benchmark_result(
            result_id=index,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            tokens_per_second=tps,
        )
        for index, tps in enumerate((40.0, 44.0, 42.0, 120.0), start=1)
    )
    model_b_rows = tuple(
        make_benchmark_result(
            result_id=index,
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            tokens_per_second=tps,
        )
        for index, tps in enumerate((28.0, 30.0, 29.0, 31.0), start=5)
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.AVG_TPS_PER_MODEL,
        run_mode=RunMode.TASKS,
        results=model_a_rows + model_b_rows,
        tasks=(task,),
        filters=ChartFilters(),
    )

    # Assert
    assert result == ChartData(
        chart_kind=ChartKind.AVG_TPS_PER_MODEL,
        categories=(_LABEL_A, _LABEL_B),
        series=(
            ChartSeries(
                name="Avg TPS",
                values=(61.5, 29.5),
                sample_sizes=(4, 4),
                low_sample_flags=(True, True),
                estimated_flags=(False, False),
                reasoning_flags=(False, False),
            ),
        ),
        x_axis_title="Model",
        y_axis_title="Tokens per second",
        value_unit="tok/s",
    )


def test_avg_time_per_model_matches_fixture() -> None:
    """Proves: STORY-033-AC-1

    Given completed rows with non-null `total_time_ms` for two models, when
    `AVG_TIME_PER_MODEL` is computed, then the resulting `ChartData` matches
    the §7.3 catalog computation — mean `total_time_ms` divided by 1000 (CA-6
    neighbours; direct §7.3 case).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = (
        make_benchmark_result(
            result_id=1,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            total_time_ms=3000,
        ),
        make_benchmark_result(
            result_id=2,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            total_time_ms=5000,
        ),
        make_benchmark_result(
            result_id=3,
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            total_time_ms=2000,
        ),
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.AVG_TIME_PER_MODEL,
        run_mode=RunMode.TASKS,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(),
    )

    # Assert
    assert result == ChartData(
        chart_kind=ChartKind.AVG_TIME_PER_MODEL,
        categories=(_LABEL_A, _LABEL_B),
        series=(
            ChartSeries(
                name="Avg time",
                values=(4.0, 2.0),
                sample_sizes=(2, 1),
                low_sample_flags=(True, True),
            ),
        ),
        x_axis_title="Model",
        y_axis_title="Total time",
        value_unit="s",
    )


def test_success_failed_incomplete_stacked_matches_fixture() -> None:
    """Proves: STORY-033-AC-1

    Given a mix of completed, failed, and pending rows across two models,
    when `SUCCESS_FAILED_INCOMPLETE_STACKED` is computed, then the resulting
    `ChartData` carries three per-model counts that sum to each model's row
    count (§7.4, CA-6).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = (
        make_benchmark_result(
            result_id=1,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            status=ResultStatus.COMPLETED,
        ),
        make_benchmark_result(
            result_id=2,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            status=ResultStatus.COMPLETED,
        ),
        make_benchmark_result(
            result_id=3,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            status=ResultStatus.FAILED_INFERENCE,
        ),
        make_benchmark_result(
            result_id=4,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            status=ResultStatus.PENDING,
        ),
        make_benchmark_result(
            result_id=5,
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            status=ResultStatus.COMPLETED,
        ),
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.SUCCESS_FAILED_INCOMPLETE_STACKED,
        run_mode=RunMode.TASKS,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(),
    )

    # Assert
    assert result == ChartData(
        chart_kind=ChartKind.SUCCESS_FAILED_INCOMPLETE_STACKED,
        categories=(_LABEL_A, _LABEL_B),
        series=(
            ChartSeries(name="Succeeded", values=(2.0, 1.0)),
            ChartSeries(name="Failed", values=(1.0, 0.0)),
            ChartSeries(name="Incomplete", values=(1.0, 0.0)),
        ),
        x_axis_title="Model",
        y_axis_title="Task count",
    )


def test_pass_rate_by_model_matches_fixture() -> None:
    """Proves: STORY-033-AC-1

    Given completed rows with verdicts for two models, when
    `PASS_RATE_BY_MODEL` is computed with the default *count ungraded as
    not-pass* toggle, then the resulting `ChartData` matches the §7.5
    catalog computation exactly (CA-9).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = (
        make_benchmark_result(
            result_id=1,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            verdict=Verdict.PASS,
        ),
        make_benchmark_result(
            result_id=2,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            verdict=Verdict.PASS,
        ),
        make_benchmark_result(
            result_id=3,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            verdict=Verdict.FAIL,
        ),
        make_benchmark_result(
            result_id=4,
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            verdict=Verdict.PASS,
        ),
        make_benchmark_result(
            result_id=5,
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            verdict=None,
        ),
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.PASS_RATE_BY_MODEL,
        run_mode=RunMode.GRADED,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(),
    )

    # Assert
    assert result == ChartData(
        chart_kind=ChartKind.PASS_RATE_BY_MODEL,
        categories=(_LABEL_A, _LABEL_B),
        series=(
            ChartSeries(
                name="Pass rate",
                values=(2 / 3, 0.5),
                sample_sizes=(3, 2),
                low_sample_flags=(True, True),
            ),
        ),
        x_axis_title="Model",
        y_axis_title="Pass rate",
    )


def test_avg_cosine_by_model_matches_fixture() -> None:
    """Proves: STORY-033-AC-1

    Given completed rows with `cosine_similarity` for two models, when
    `AVG_COSINE_BY_MODEL` is computed with the default *fold ungraded as
    0.0* OFF, then the resulting `ChartData` matches the §7.6 catalog
    computation — the mean over non-null Cosine Scores only (CA-12).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = (
        make_benchmark_result(
            result_id=1,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            cosine_similarity=0.8,
        ),
        make_benchmark_result(
            result_id=2,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            cosine_similarity=0.9,
        ),
        make_benchmark_result(
            result_id=3,
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            cosine_similarity=0.7,
        ),
        make_benchmark_result(
            result_id=4,
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            cosine_similarity=None,
        ),
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.AVG_COSINE_BY_MODEL,
        run_mode=RunMode.GRADED,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(),
    )

    # Assert
    assert result == ChartData(
        chart_kind=ChartKind.AVG_COSINE_BY_MODEL,
        categories=(_LABEL_A, _LABEL_B),
        series=(
            ChartSeries(
                name="Avg Cosine Score",
                values=(0.8500000000000001, 0.7),
                sample_sizes=(2, 1),
                low_sample_flags=(True, True),
            ),
        ),
        x_axis_title="Model",
        y_axis_title="Cosine Score",
    )


def test_verdict_counts_stacked_matches_fixture() -> None:
    """Proves: STORY-033-AC-1

    Given completed rows with a mix of pass/fail/ungraded verdicts across
    two models, when `VERDICT_COUNTS_STACKED` is computed, then the
    resulting `ChartData` carries three per-model verdict counts matching
    the §7.7 catalog computation exactly (CA-14).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = (
        make_benchmark_result(
            result_id=1,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            verdict=Verdict.PASS,
        ),
        make_benchmark_result(
            result_id=2,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            verdict=Verdict.PASS,
        ),
        make_benchmark_result(
            result_id=3,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            verdict=Verdict.FAIL,
        ),
        make_benchmark_result(
            result_id=4,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            verdict=None,
        ),
        make_benchmark_result(
            result_id=5,
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            verdict=Verdict.PASS,
        ),
        make_benchmark_result(
            result_id=6,
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            verdict=None,
        ),
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.VERDICT_COUNTS_STACKED,
        run_mode=RunMode.GRADED,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(),
    )

    # Assert
    assert result == ChartData(
        chart_kind=ChartKind.VERDICT_COUNTS_STACKED,
        categories=(_LABEL_A, _LABEL_B),
        series=(
            ChartSeries(name="Pass", values=(2.0, 1.0)),
            ChartSeries(name="Fail", values=(1.0, 0.0)),
            ChartSeries(name="Ungraded", values=(1.0, 1.0)),
        ),
        x_axis_title="Model",
        y_axis_title="Result count",
    )


def test_time_vs_tokens_scatter_matches_fixture() -> None:
    """Proves: STORY-033-AC-1

    Given completed rows carrying both `completion_tokens` and
    `total_time_ms` for two models, when `TIME_VS_TOKENS_SCATTER` is
    computed, then each model contributes a token-series/second-series pair
    with matching `result_ids`, per the coder's two-series-per-model
    representation of §7.8 (CA-15, CA-16).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = (
        make_benchmark_result(
            result_id=1,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            completion_tokens=100,
            total_time_ms=2000,
        ),
        make_benchmark_result(
            result_id=2,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            completion_tokens=150,
            total_time_ms=3000,
        ),
        make_benchmark_result(
            result_id=3,
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            completion_tokens=200,
            total_time_ms=4000,
        ),
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.TIME_VS_TOKENS_SCATTER,
        run_mode=RunMode.TASKS,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(),
    )

    # Assert
    assert result == ChartData(
        chart_kind=ChartKind.TIME_VS_TOKENS_SCATTER,
        categories=(),
        series=(
            ChartSeries(name=f"{_LABEL_A} (tokens)", values=(100.0, 150.0), result_ids=(1, 2)),
            ChartSeries(name=f"{_LABEL_A} (seconds)", values=(2.0, 3.0), result_ids=(1, 2)),
            ChartSeries(name=f"{_LABEL_B} (tokens)", values=(200.0,), result_ids=(3,)),
            ChartSeries(name=f"{_LABEL_B} (seconds)", values=(4.0,), result_ids=(3,)),
        ),
        x_axis_title="Completion tokens",
        y_axis_title="Total time",
        value_unit="s",
    )


def test_heatmap_task_by_model_matches_fixture() -> None:
    """Proves: STORY-033-AC-1

    Given two tasks and two models, one `(task, model)` pair with no
    completed result, when `HEATMAP_TASK_BY_MODEL` is computed with the
    default *verdict* cell value, then the resulting `HeatmapData` matrix
    encodes PASS/FAIL as 1.0/0.0 and the missing pair as `None` (§7.9,
    CA-17).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task_one = make_benchmark_task(task_id="task-1", task_order=0)
    task_two = make_benchmark_task(task_id="task-2", task_order=1)
    rows = (
        make_benchmark_result(
            result_id=1,
            task_id="task-1",
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            verdict=Verdict.PASS,
        ),
        make_benchmark_result(
            result_id=2,
            task_id="task-1",
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            verdict=Verdict.FAIL,
        ),
        make_benchmark_result(
            result_id=3,
            task_id="task-2",
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            verdict=Verdict.PASS,
        ),
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.HEATMAP_TASK_BY_MODEL,
        run_mode=RunMode.GRADED,
        results=rows,
        tasks=(task_one, task_two),
        filters=ChartFilters(),
    )

    # Assert
    assert result == HeatmapData(
        row_labels=("task-1", "task-2"),
        column_labels=(_LABEL_A, _LABEL_B),
        cells=((1.0, 0.0), (None, 1.0)),
    )


def test_per_category_bar_matches_fixture() -> None:
    """Proves: STORY-033-AC-1

    Given two task categories and two models with different per-category
    coverage, when `PER_CATEGORY_BAR` is computed with the default *Pass
    rate* metric, then the resulting `ChartData` groups by category with
    one series per model, `None` where a model has no rows in a category
    (§7.10, CA-20).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task_cat1 = make_benchmark_task(task_id="cat1-task", category="Cat1")
    task_cat2 = make_benchmark_task(task_id="cat2-task", category="Cat2")
    rows = (
        make_benchmark_result(
            result_id=1,
            task_id="cat1-task",
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            verdict=Verdict.PASS,
        ),
        make_benchmark_result(
            result_id=2,
            task_id="cat1-task",
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            verdict=Verdict.PASS,
        ),
        make_benchmark_result(
            result_id=3,
            task_id="cat1-task",
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            verdict=Verdict.FAIL,
        ),
        make_benchmark_result(
            result_id=4,
            task_id="cat2-task",
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            verdict=Verdict.PASS,
        ),
        make_benchmark_result(
            result_id=5,
            task_id="cat2-task",
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            verdict=Verdict.PASS,
        ),
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.PER_CATEGORY_BAR,
        run_mode=RunMode.GRADED,
        results=rows,
        tasks=(task_cat1, task_cat2),
        filters=ChartFilters(),
    )

    # Assert
    assert result == ChartData(
        chart_kind=ChartKind.PER_CATEGORY_BAR,
        categories=("Cat1", "Cat2"),
        series=(
            ChartSeries(
                name=_LABEL_A,
                values=(1.0, None),
                sample_sizes=(2, 0),
                low_sample_flags=(True, True),
            ),
            ChartSeries(
                name=_LABEL_B,
                values=(0.0, 1.0),
                sample_sizes=(1, 2),
                low_sample_flags=(True, True),
            ),
        ),
        x_axis_title="Category",
        y_axis_title="Pass rate",
    )


def test_speed_vs_quality_scatter_matches_fixture() -> None:
    """Proves: STORY-033-AC-1

    Given two models with completed, graded rows, when
    `SPEED_VS_QUALITY_SCATTER` is computed with the default *Pass rate*
    Y-metric, then the resulting `ChartData` carries one point per model
    and the Pareto frontier excludes the dominated model (§7.11, CA-21).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = (
        make_benchmark_result(
            result_id=1,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            tokens_per_second=50.0,
            verdict=Verdict.PASS,
        ),
        make_benchmark_result(
            result_id=2,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            tokens_per_second=60.0,
            verdict=Verdict.PASS,
        ),
        make_benchmark_result(
            result_id=3,
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            tokens_per_second=20.0,
            verdict=Verdict.FAIL,
        ),
        make_benchmark_result(
            result_id=4,
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            tokens_per_second=20.0,
            verdict=Verdict.FAIL,
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
    assert result == ChartData(
        chart_kind=ChartKind.SPEED_VS_QUALITY_SCATTER,
        categories=(_LABEL_A, _LABEL_B),
        series=(
            ChartSeries(
                name="Tokens/sec",
                values=(55.0, 20.0),
                sample_sizes=(2, 2),
                low_sample_flags=(True, True),
            ),
            ChartSeries(
                name="Pass rate",
                values=(1.0, 0.0),
                sample_sizes=(2, 2),
                low_sample_flags=(True, True),
            ),
        ),
        x_axis_title="Tokens/sec",
        y_axis_title="Pass rate",
        pareto_points=((55.0, 1.0),),
    )


def test_tokens_per_task_box_matches_fixture() -> None:
    """Proves: STORY-033-AC-1

    Given one model with a long-tail outlier in `completion_tokens` and one
    model with a single value, when `TOKENS_PER_TASK_BOX` is computed with
    the default *Show outliers* ON, then the resulting `ChartData` carries
    a five-number summary per model computed over non-outlier values plus a
    separate outlier series with its `result_id` (§7.12, CA-23).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    model_a_tokens = (10, 12, 14, 16, 18, 20, 1000)
    model_a_rows = tuple(
        make_benchmark_result(
            result_id=index,
            provider_id=_PROVIDER_A_ID,
            provider_name=_PROVIDER_A_NAME,
            model_name=_MODEL_A,
            completion_tokens=tokens,
        )
        for index, tokens in enumerate(model_a_tokens, start=1)
    )
    model_b_rows = (
        make_benchmark_result(
            result_id=8,
            provider_id=_PROVIDER_B_ID,
            provider_name=_PROVIDER_B_NAME,
            model_name=_MODEL_B,
            completion_tokens=50,
        ),
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.TOKENS_PER_TASK_BOX,
        run_mode=RunMode.TASKS,
        results=model_a_rows + model_b_rows,
        tasks=(task,),
        filters=ChartFilters(),
    )

    # Assert
    assert result == ChartData(
        chart_kind=ChartKind.TOKENS_PER_TASK_BOX,
        categories=(_LABEL_A, _LABEL_B),
        series=(
            ChartSeries(
                name="min", values=(10.0, 50.0), sample_sizes=(6, 1), low_sample_flags=(False, True)
            ),
            ChartSeries(
                name="q1", values=(11.5, 50.0), sample_sizes=(6, 1), low_sample_flags=(False, True)
            ),
            ChartSeries(
                name="median",
                values=(15.0, 50.0),
                sample_sizes=(6, 1),
                low_sample_flags=(False, True),
            ),
            ChartSeries(
                name="q3", values=(18.5, 50.0), sample_sizes=(6, 1), low_sample_flags=(False, True)
            ),
            ChartSeries(
                name="max", values=(20.0, 50.0), sample_sizes=(6, 1), low_sample_flags=(False, True)
            ),
            ChartSeries(name=f"{_LABEL_A} (outliers)", values=(1000.0,), result_ids=(7,)),
        ),
        x_axis_title="Model",
        y_axis_title="Completion tokens",
    )
