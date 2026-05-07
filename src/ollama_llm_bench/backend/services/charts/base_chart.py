"""Pure-Python data structures and ABC for chart aggregation — no Qt imports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

from ollama_llm_bench.backend.core.models import BenchmarkResult, BenchmarkRun


@dataclass(frozen=True, slots=True, kw_only=True)
class FilterDescriptor:
    """Describes a single filter control that a chart exposes in its filter row."""

    field_id: str
    label: str
    kind: Literal["multi_check", "toggle", "combo"]
    options: tuple[str, ...] = ()
    default: object = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ChartFilters:
    """Immutable filter state passed to an aggregator's compute_data method."""

    included_models: frozenset[str]
    included_categories: frozenset[str]
    included_layers: frozenset[str]
    extra: dict[str, object] = field(default_factory=dict)

    @classmethod
    def all_included(
        cls,
        *,
        models: list[str],
        categories: list[str],
        layers: list[str],
    ) -> ChartFilters:
        """Build a default 'all included' filter from the given option lists."""
        return cls(
            included_models=frozenset(models),
            included_categories=frozenset(categories),
            included_layers=frozenset(layers),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class HeatmapData:
    """Grid data for the per-task heatmap (Chart 9)."""

    row_labels: tuple[str, ...]
    col_labels: tuple[str, ...]
    cells: dict[tuple[str, str], float | None]


@dataclass(frozen=True, slots=True, kw_only=True)
class ChartData:
    """Aggregated output from a BaseChartAggregator, consumed by the chart rendering layer."""

    series_labels: tuple[str, ...] = ()
    category_labels: tuple[str, ...] = ()
    series_data: tuple[tuple[float, ...], ...] = ()
    series_stdev: tuple[float, ...] = ()
    scatter_points: tuple[tuple[float, float, str], ...] = ()
    box_sets: tuple[tuple[float, float, float, float, float], ...] = ()
    heatmap: HeatmapData | None = None
    empty_state_message: str = ""
    footnote: str = ""
    extra: dict[str, object] = field(default_factory=dict)


class BaseChartAggregator(ABC):
    """Abstract base class for pure-Python chart data aggregators."""

    @abstractmethod
    def required_filters(self) -> tuple[FilterDescriptor, ...]:
        """Return filter descriptors that define the chart's filter row UI."""

    @abstractmethod
    def compute_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
        filters: ChartFilters,
    ) -> ChartData:
        """Aggregate results into chart-ready data given the active filters.

        Args:
            run: The selected BenchmarkRun, or None if none selected.
            results: All BenchmarkResult rows for this run.
            filters: Active filter state from the chart's filter row.

        Returns:
            Aggregated ChartData for rendering.
        """
