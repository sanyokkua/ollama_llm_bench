"""Chart aggregation service (Qt-free).

Source of truth: `docs/v3_specification/11_Services_and_Algorithms/13_CHART_AGGREGATORS.md`.
Computes the twelve `ChartKind` aggregations from a run's `BenchmarkResult` snapshot
into plot-ready `ChartData`/`HeatmapData` structures: the mode gate, the five
global filters, the per-chart status pre-filter, per-chart options, stable
grouping, the minimum-sample-size guard, IQR outlier handling, and the Pareto
frontier. Pure, stateless, Qt-free; performs no I/O and emits no rendering
instructions — colours, axis scale, and canvas painting are owned by `ui/results/`.
"""

from ollama_llm_bench.backend.charts.api import make_chart_aggregator
from ollama_llm_bench.backend.charts.protocols import ChartAggregator

__all__: list[str] = [
    "ChartAggregator",
    "make_chart_aggregator",
]
