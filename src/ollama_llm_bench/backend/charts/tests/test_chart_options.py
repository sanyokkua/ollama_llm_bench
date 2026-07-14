"""Per-chart option out-of-domain fallback (`13_CHART_AGGREGATORS.md` §6.4, §9, CA-29)."""

import pytest
import structlog.testing

from ollama_llm_bench.backend.charts import make_chart_aggregator
from ollama_llm_bench.backend.charts.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    ChartData,
    ChartFilters,
    ChartKind,
    RunMode,
)

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME = "model-a"

# Crafted so the IQR x 1.5 fence flags 100000 as an outlier: dropping it (the
# documented `drop_outliers` default of True) yields a materially different mean
# (100.5) than keeping it (~14371.86) — a wrong fallback is caught, not masked.
_TTFT_VALUES_WITH_OUTLIER = (100, 102, 101, 103, 99, 98, 100000)
_TTFT_MEAN_DROPPING_OUTLIER = 100.5

# Crafted so `mean` (the documented default) and `median` disagree (40.0 vs 25.0) —
# a wrong aggregation fallback is caught, not masked.
_TPS_VALUES = (10.0, 20.0, 30.0, 100.0)
_TPS_MEAN = 40.0


def _ttft_outlier_rows() -> tuple[BenchmarkResult, ...]:
    return tuple(
        make_benchmark_result(
            result_id=index, provider_id=_PROVIDER_ID, model_name=_MODEL_NAME, ttft_ms=value
        )
        for index, value in enumerate(_TTFT_VALUES_WITH_OUTLIER, start=1)
    )


def _tps_rows() -> tuple[BenchmarkResult, ...]:
    return tuple(
        make_benchmark_result(
            result_id=index,
            provider_id=_PROVIDER_ID,
            model_name=_MODEL_NAME,
            tokens_per_second=value,
        )
        for index, value in enumerate(_TPS_VALUES, start=1)
    )


@pytest.mark.parametrize(
    "chart_kind,rows,option_name,invalid_value,expected_value",
    [
        pytest.param(
            ChartKind.AVG_TTFT_PER_MODEL,
            _ttft_outlier_rows(),
            "drop_outliers",
            "not-a-bool",
            _TTFT_MEAN_DROPPING_OUTLIER,
            id="bool_option_wrong_type_falls_back_to_true",
        ),
        pytest.param(
            ChartKind.AVG_TPS_PER_MODEL,
            _tps_rows(),
            "aggregation",
            "bogus",
            _TPS_MEAN,
            id="enum_option_out_of_domain_falls_back_to_mean",
        ),
    ],
)
def test_out_of_domain_option_uses_documented_default(
    chart_kind: ChartKind,
    rows: tuple[BenchmarkResult, ...],
    option_name: str,
    invalid_value: str,
    expected_value: float,
) -> None:
    """Proves: STORY-033-AC-8

    Given a per-chart option value outside its documented domain — a non-bool
    value for a boolean toggle, or a string outside a string domain — when the
    aggregator runs, then the value is replaced by that option's documented
    default: the resulting statistic matches the value computed under the
    documented default and is identical to the structure produced when the
    option is omitted entirely (§6.4, §9, CA-29).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()

    # Act
    with_invalid_value = aggregator.compute(
        chart_kind=chart_kind,
        run_mode=RunMode.TASKS,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(options={option_name: invalid_value}),
    )
    with_option_omitted = aggregator.compute(
        chart_kind=chart_kind,
        run_mode=RunMode.TASKS,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(),
    )

    # Assert
    assert isinstance(with_invalid_value, ChartData)
    assert with_invalid_value.series[0].values[0] == pytest.approx(expected_value)
    assert with_invalid_value == with_option_omitted


@pytest.mark.parametrize(
    "chart_kind,rows,option_name,invalid_value",
    [
        pytest.param(
            ChartKind.AVG_TTFT_PER_MODEL,
            _ttft_outlier_rows(),
            "drop_outliers",
            "not-a-bool",
            id="bool_option_wrong_type_logs_warning",
        ),
        pytest.param(
            ChartKind.AVG_TPS_PER_MODEL,
            _tps_rows(),
            "aggregation",
            "bogus",
            id="enum_option_out_of_domain_logs_warning",
        ),
    ],
)
def test_out_of_domain_option_logs_a_one_time_warning(
    chart_kind: ChartKind,
    rows: tuple[BenchmarkResult, ...],
    option_name: str,
    invalid_value: str,
) -> None:
    """Proves: STORY-033-AC-8

    Given a per-chart option value outside its documented domain, when the
    aggregator runs, then exactly one `chart_option_out_of_domain` warning is
    logged, naming the chart kind, the option, and the invalid value (§6.4,
    §9, CA-29).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()

    # Act
    with structlog.testing.capture_logs() as captured_logs:
        aggregator.compute(
            chart_kind=chart_kind,
            run_mode=RunMode.TASKS,
            results=rows,
            tasks=(task,),
            filters=ChartFilters(options={option_name: invalid_value}),
        )

    # Assert
    warning_logs = [entry for entry in captured_logs if entry["log_level"] == "warning"]
    assert len(warning_logs) == 1
    assert warning_logs[0]["event"] == "chart_option_out_of_domain"
    assert warning_logs[0]["chart_kind"] == chart_kind.value
    assert warning_logs[0]["option_name"] == option_name
    assert warning_logs[0]["invalid_value"] == invalid_value
