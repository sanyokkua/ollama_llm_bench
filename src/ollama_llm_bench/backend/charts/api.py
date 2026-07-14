"""Public factory for the Chart Aggregation Service (`13_CHART_AGGREGATORS.md` §2)."""

import icontract

from ollama_llm_bench.backend.charts._internal.dispatch import _ChartAggregatorImpl
from ollama_llm_bench.backend.charts.protocols import ChartAggregator

__all__: list[str] = ["make_chart_aggregator"]


@icontract.ensure(lambda result: result is not None)
def make_chart_aggregator() -> ChartAggregator:
    """Construct the stateless Chart Aggregation Service (§10).

    Returns:
        A pure, stateless `ChartAggregator`; the same inputs always yield an
        identical structure and it is safe to call from any thread.
    """
    return _ChartAggregatorImpl()
