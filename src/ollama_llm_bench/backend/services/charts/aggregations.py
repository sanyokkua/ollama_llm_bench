"""Concrete BaseChartAggregator implementations for all 12 charts — pure Python, no Qt imports."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Callable
from typing import override

from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkRun,
    RunMode,
)
from ollama_llm_bench.backend.services.charts.base_chart import (
    BaseChartAggregator,
    ChartData,
    ChartFilters,
    FilterDescriptor,
    HeatmapData,
)

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _filter_results(
    results: list[BenchmarkResult],
    filters: ChartFilters,
    *,
    require_completed: bool = True,
) -> list[BenchmarkResult]:
    """Apply model/category/layer filters and optionally require COMPLETED status.

    Args:
        results: Full result list for the run.
        filters: Active filter state.
        require_completed: When True, only rows with status==COMPLETED are kept.

    Returns:
        Filtered subset of results.
    """
    rows = results
    if require_completed:
        rows = [r for r in rows if r.status == BenchmarkResultStatus.COMPLETED]
    if filters.included_models:
        rows = [r for r in rows if r.model_name in filters.included_models]
    if filters.included_categories:
        rows = [r for r in rows if r.task_category in filters.included_categories]
    if filters.included_layers:
        rows = [r for r in rows if r.resolution_layer in filters.included_layers]
    return rows


def _to_float(val: int | float | None) -> float:
    """Type-safe coercion for pre-filtered fields where None has been excluded."""
    return float(val) if val is not None else 0.0


def _group_by_model(
    rows: list[BenchmarkResult],
    value_fn: Callable[[BenchmarkResult], float],
) -> dict[str, list[float]]:
    """Group rows by model_name, applying value_fn to get a float.

    Args:
        rows: Pre-filtered result rows.
        value_fn: Callable accepting BenchmarkResult and returning float.

    Returns:
        Mapping of model_name to list of float values.
    """
    grouped: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        grouped[r.model_name].append(value_fn(r))
    return dict(grouped)


# ---------------------------------------------------------------------------
# Chart 1 — TTFT per model
# ---------------------------------------------------------------------------


class Chart1TtftAggregator(BaseChartAggregator):
    """Average TTFT (ms) per model — streaming runs only."""

    @override
    def required_filters(self) -> tuple[FilterDescriptor, ...]:
        """Return filter descriptors for model and task_category multi-check filters."""
        return (
            FilterDescriptor(field_id="model_name", label="Models", kind="multi_check"),
            FilterDescriptor(field_id="task_category", label="Category", kind="multi_check"),
        )

    @override
    def compute_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
        filters: ChartFilters,
    ) -> ChartData:
        """Compute average TTFT (ms) grouped by model, sorted ascending."""
        total = [r for r in results if r.status == BenchmarkResultStatus.COMPLETED and not r.has_inference_error]
        valid = [r for r in total if r.ttft_ms is not None]
        excluded = len(total) - len(valid)

        if filters.included_models:
            valid = [r for r in valid if r.model_name in filters.included_models]
        if filters.included_categories:
            valid = [r for r in valid if r.task_category in filters.included_categories]

        if not valid:
            return ChartData(empty_state_message="TTFT only available in streaming runs.")

        grouped = _group_by_model(valid, lambda r: _to_float(r.ttft_ms))
        sorted_models = sorted(grouped, key=lambda m: statistics.mean(grouped[m]))
        values = tuple(statistics.mean(grouped[m]) for m in sorted_models)
        footnote = f"Excluded {excluded} rows with null TTFT." if excluded > 0 else ""
        return ChartData(
            series_labels=("Avg TTFT (ms)",),
            category_labels=tuple(sorted_models),
            series_data=(values,),
            footnote=footnote,
        )


# ---------------------------------------------------------------------------
# Chart 2 — Tokens per second per model
# ---------------------------------------------------------------------------


class Chart2TpsAggregator(BaseChartAggregator):
    """Average tokens-per-second per model, sorted descending."""

    @override
    def required_filters(self) -> tuple[FilterDescriptor, ...]:
        """Return filter descriptors for model and task_category multi-check filters."""
        return (
            FilterDescriptor(field_id="model_name", label="Models", kind="multi_check"),
            FilterDescriptor(field_id="task_category", label="Category", kind="multi_check"),
        )

    @override
    def compute_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
        filters: ChartFilters,
    ) -> ChartData:
        """Compute average tokens/s grouped by model, sorted descending."""
        total = [r for r in results if r.status == BenchmarkResultStatus.COMPLETED and not r.has_inference_error]
        valid = [r for r in total if r.tokens_per_second is not None and r.tokens_per_second > 0]
        excluded = len(total) - len(valid)

        if filters.included_models:
            valid = [r for r in valid if r.model_name in filters.included_models]
        if filters.included_categories:
            valid = [r for r in valid if r.task_category in filters.included_categories]

        if not valid:
            return ChartData(empty_state_message="No tokens-per-second data available.")

        grouped = _group_by_model(valid, lambda r: _to_float(r.tokens_per_second))
        sorted_models = sorted(grouped, key=lambda m: statistics.mean(grouped[m]), reverse=True)
        values = tuple(statistics.mean(grouped[m]) for m in sorted_models)
        footnote = f"Excluded {excluded} rows with zero or null TPS." if excluded > 0 else ""
        return ChartData(
            series_labels=("Avg Tokens/s",),
            category_labels=tuple(sorted_models),
            series_data=(values,),
            footnote=footnote,
        )


# ---------------------------------------------------------------------------
# Chart 3 — Total inference time per model (optional outlier removal)
# ---------------------------------------------------------------------------


class Chart3TimeAggregator(BaseChartAggregator):
    """Average total inference time (ms) per model, with optional outlier trimming."""

    @override
    def required_filters(self) -> tuple[FilterDescriptor, ...]:
        """Return filter descriptors including an exclude_outliers toggle."""
        return (
            FilterDescriptor(field_id="model_name", label="Models", kind="multi_check"),
            FilterDescriptor(field_id="task_category", label="Category", kind="multi_check"),
            FilterDescriptor(field_id="exclude_outliers", label="Exclude Outliers", kind="toggle", default=False),
        )

    @override
    def compute_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
        filters: ChartFilters,
    ) -> ChartData:
        """Compute average total_time_ms per model, optionally dropping top-10% outliers."""
        base = [r for r in results if r.status == BenchmarkResultStatus.COMPLETED and not r.has_inference_error]
        valid = [r for r in base if r.total_time_ms is not None]

        if filters.included_models:
            valid = [r for r in valid if r.model_name in filters.included_models]
        if filters.included_categories:
            valid = [r for r in valid if r.task_category in filters.included_categories]

        if not valid:
            return ChartData(empty_state_message="No inference time data available.")

        exclude_outliers = bool(filters.extra.get("exclude_outliers", False))
        raw_grouped = _group_by_model(valid, lambda r: _to_float(r.total_time_ms))

        total_dropped = 0
        trimmed: dict[str, list[float]] = {}
        for model, vals in raw_grouped.items():
            if exclude_outliers and len(vals) > 1:
                drop_n = math.ceil(len(vals) * 0.1)
                sorted_vals = sorted(vals)
                trimmed[model] = sorted_vals[: len(sorted_vals) - drop_n]
                total_dropped += drop_n
            else:
                trimmed[model] = vals

        sorted_models = sorted(trimmed, key=lambda m: statistics.mean(trimmed[m]))
        values = tuple(statistics.mean(trimmed[m]) for m in sorted_models)
        footnote = f"Dropped {total_dropped} outlier rows (top 10% per model)." if total_dropped > 0 else ""
        return ChartData(
            series_labels=("Avg Time (ms)",),
            category_labels=tuple(sorted_models),
            series_data=(values,),
            footnote=footnote,
        )


# ---------------------------------------------------------------------------
# Chart 4 — Success vs Failed counts per model
# ---------------------------------------------------------------------------


class Chart4SuccessFailedAggregator(BaseChartAggregator):
    """Stacked bar: successful vs failed results per model."""

    @override
    def required_filters(self) -> tuple[FilterDescriptor, ...]:
        """Return filter descriptors for model multi-check and error_type combo."""
        return (
            FilterDescriptor(field_id="model_name", label="Models", kind="multi_check"),
            FilterDescriptor(
                field_id="error_type",
                label="Error Type",
                kind="combo",
                options=("either", "inference_only", "judge_only"),
                default="either",
            ),
        )

    @override
    def compute_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
        filters: ChartFilters,
    ) -> ChartData:
        """Count successful and failed results per model."""
        rows = results
        if filters.included_models:
            rows = [r for r in rows if r.model_name in filters.included_models]

        error_type = str(filters.extra.get("error_type", "either"))
        all_models = sorted({r.model_name for r in rows})

        successful_counts: list[float] = []
        failed_counts: list[float] = []
        for model in all_models:
            model_rows = [r for r in rows if r.model_name == model]
            successful = sum(
                1
                for r in model_rows
                if not r.has_inference_error and not r.has_judge_error and r.status == BenchmarkResultStatus.COMPLETED
            )
            if error_type == "inference_only":
                failed = sum(1 for r in model_rows if r.has_inference_error)
            elif error_type == "judge_only":
                failed = sum(1 for r in model_rows if r.has_judge_error)
            else:
                failed = sum(
                    1
                    for r in model_rows
                    if r.has_inference_error or r.has_judge_error or r.status == BenchmarkResultStatus.FAILED
                )
            successful_counts.append(float(successful))
            failed_counts.append(float(failed))

        if not all_models:
            return ChartData(empty_state_message="No results available.")

        return ChartData(
            series_labels=("Successful", "Failed"),
            category_labels=tuple(all_models),
            series_data=(tuple(successful_counts), tuple(failed_counts)),
        )


# ---------------------------------------------------------------------------
# Chart 5 — Pass rate per model
# ---------------------------------------------------------------------------


class Chart5PassRateAggregator(BaseChartAggregator):
    """Pass rate (%) per model — unavailable in Speed mode."""

    @override
    def required_filters(self) -> tuple[FilterDescriptor, ...]:
        """Return filter descriptors for model and resolution_layer multi-check filters."""
        return (
            FilterDescriptor(field_id="model_name", label="Models", kind="multi_check"),
            FilterDescriptor(field_id="resolution_layer", label="Resolution Layer", kind="multi_check"),
        )

    @override
    def compute_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
        filters: ChartFilters,
    ) -> ChartData:
        """Compute pass rate percentage per model, sorted descending."""
        if run is not None and run.run_mode == RunMode.SPEED:
            return ChartData(empty_state_message="Pass rate is not available for Speed mode runs (no judging).")

        rows = [r for r in results if r.final_verdict is not None and r.status == BenchmarkResultStatus.COMPLETED]
        if filters.included_models:
            rows = [r for r in rows if r.model_name in filters.included_models]
        if filters.included_layers:
            rows = [r for r in rows if r.resolution_layer in filters.included_layers]

        if not rows:
            return ChartData(empty_state_message="No verdict data available.")

        all_models = sorted({r.model_name for r in rows})
        rates: list[float] = []
        for model in all_models:
            model_rows = [r for r in rows if r.model_name == model]
            pass_count = sum(1 for r in model_rows if r.final_verdict == "pass")
            rates.append(pass_count / len(model_rows) * 100.0)

        sorted_pairs = sorted(zip(all_models, rates, strict=False), key=lambda p: p[1], reverse=True)
        sorted_models = [p[0] for p in sorted_pairs]
        sorted_rates = [p[1] for p in sorted_pairs]

        return ChartData(
            series_labels=("Pass Rate (%)",),
            category_labels=tuple(sorted_models),
            series_data=(tuple(sorted_rates),),
        )


# ---------------------------------------------------------------------------
# Chart 6 — Average judge score per model
# ---------------------------------------------------------------------------


class Chart6AvgGradeAggregator(BaseChartAggregator):
    """Average judge score per model with optional standard deviation band."""

    @override
    def required_filters(self) -> tuple[FilterDescriptor, ...]:
        """Return filter descriptors for model and resolution_layer multi-check filters."""
        return (
            FilterDescriptor(field_id="model_name", label="Models", kind="multi_check"),
            FilterDescriptor(field_id="resolution_layer", label="Resolution Layer", kind="multi_check"),
        )

    @override
    def compute_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
        filters: ChartFilters,
    ) -> ChartData:
        """Compute mean judge_score per model, with stdev when data allows."""
        all_rows = [r for r in results if not r.has_judge_error]
        null_excluded = sum(1 for r in all_rows if r.judge_score is None)
        valid = [r for r in all_rows if r.judge_score is not None]

        if filters.included_models:
            valid = [r for r in valid if r.model_name in filters.included_models]
        if filters.included_layers:
            valid = [r for r in valid if r.resolution_layer in filters.included_layers]

        if not valid:
            return ChartData(empty_state_message="No judge score data available.")

        grouped = _group_by_model(valid, lambda r: _to_float(r.judge_score))
        sorted_models = sorted(grouped, key=lambda m: statistics.mean(grouped[m]), reverse=True)
        means = tuple(statistics.mean(grouped[m]) for m in sorted_models)
        stdevs = tuple(statistics.stdev(grouped[m]) if len(grouped[m]) > 1 else 0.0 for m in sorted_models)
        footnote = f"Excluded {null_excluded} rows with null judge score." if null_excluded > 0 else ""
        return ChartData(
            series_labels=("Avg Judge Score",),
            category_labels=tuple(sorted_models),
            series_data=(means,),
            series_stdev=stdevs,
            footnote=footnote,
        )


# ---------------------------------------------------------------------------
# Chart 7 — Verdict counts (stacked by verdict or resolution layer)
# ---------------------------------------------------------------------------


class Chart7VerdictCountsAggregator(BaseChartAggregator):
    """Stacked bar of verdict counts per model, grouped by verdict or resolution layer."""

    @override
    def required_filters(self) -> tuple[FilterDescriptor, ...]:
        """Return filter descriptors for model multi-check and stack_mode combo."""
        return (
            FilterDescriptor(field_id="model_name", label="Models", kind="multi_check"),
            FilterDescriptor(
                field_id="stack_mode",
                label="Stack By",
                kind="combo",
                options=("verdict", "layer"),
                default="verdict",
            ),
        )

    @override
    def compute_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
        filters: ChartFilters,
    ) -> ChartData:
        """Compute verdict counts stacked by verdict type or resolution layer."""
        rows = [r for r in results if r.final_verdict is not None]
        if filters.included_models:
            rows = [r for r in rows if r.model_name in filters.included_models]

        if not rows:
            return ChartData(empty_state_message="No verdict data available.")

        stack_mode = str(filters.extra.get("stack_mode", "verdict"))
        all_models = sorted({r.model_name for r in rows})

        if stack_mode == "layer":
            all_layers = sorted({r.resolution_layer for r in rows if r.resolution_layer is not None})
            series_data: list[tuple[float, ...]] = []
            for layer in all_layers:
                counts = tuple(
                    float(sum(1 for r in rows if r.model_name == m and r.resolution_layer == layer)) for m in all_models
                )
                series_data.append(counts)
            return ChartData(
                series_labels=tuple(all_layers),
                category_labels=tuple(all_models),
                series_data=tuple(series_data),
            )

        # verdict mode
        pass_counts = tuple(
            float(sum(1 for r in rows if r.model_name == m and r.final_verdict == "pass")) for m in all_models
        )
        fail_counts = tuple(
            float(sum(1 for r in rows if r.model_name == m and r.final_verdict == "fail")) for m in all_models
        )
        return ChartData(
            series_labels=("PASS", "FAIL"),
            category_labels=tuple(all_models),
            series_data=(pass_counts, fail_counts),
        )


# ---------------------------------------------------------------------------
# Chart 8 — Completion tokens vs total time scatter
# ---------------------------------------------------------------------------


class Chart8TimeTokensAggregator(BaseChartAggregator):
    """Scatter: average completion tokens vs average inference time (s) per model."""

    @override
    def required_filters(self) -> tuple[FilterDescriptor, ...]:
        """Return filter descriptors for model multi-check and log_scale toggle."""
        return (
            FilterDescriptor(field_id="model_name", label="Models", kind="multi_check"),
            FilterDescriptor(field_id="log_scale", label="Log Scale", kind="toggle", default=False),
        )

    @override
    def compute_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
        filters: ChartFilters,
    ) -> ChartData:
        """Compute scatter points (avg_tokens, avg_time_s) per model."""
        valid = [
            r
            for r in results
            if r.completion_tokens is not None and r.total_time_ms is not None and not r.has_inference_error
        ]
        if filters.included_models:
            valid = [r for r in valid if r.model_name in filters.included_models]

        if not valid:
            return ChartData(empty_state_message="No token/time data available.")

        all_models = sorted({r.model_name for r in valid})
        points: list[tuple[float, float, str]] = []
        for model in all_models:
            model_rows = [r for r in valid if r.model_name == model]
            avg_tokens = statistics.mean(_to_float(r.completion_tokens) for r in model_rows)
            avg_time_s = statistics.mean(_to_float(r.total_time_ms) / 1000.0 for r in model_rows)
            points.append((avg_tokens, avg_time_s, model))

        log_scale = bool(filters.extra.get("log_scale", False))
        return ChartData(
            scatter_points=tuple(points),
            extra={"log_scale": log_scale},
        )


# ---------------------------------------------------------------------------
# Chart 9 -- Task x model heatmap
# ---------------------------------------------------------------------------


class Chart9HeatmapAggregator(BaseChartAggregator):
    """Heatmap of judge score (or verdict) per task x model cell."""

    @override
    def required_filters(self) -> tuple[FilterDescriptor, ...]:
        """Return filter descriptors for model, sort_by combo, and compact_view toggle."""
        return (
            FilterDescriptor(field_id="model_name", label="Models", kind="multi_check"),
            FilterDescriptor(
                field_id="sort_by",
                label="Sort By",
                kind="combo",
                options=("score", "alphabetical", "pass_rate"),
                default="score",
            ),
            FilterDescriptor(field_id="compact_view", label="Compact View", kind="toggle", default=False),
        )

    def _cell_value(self, r: BenchmarkResult) -> float | None:
        """Derive numeric cell value from judge_score or final_verdict."""
        if r.judge_score is not None:
            return r.judge_score
        if r.final_verdict == "pass":
            return 1.0
        if r.final_verdict == "fail":
            return 0.0
        return None

    def _sort_models(
        self,
        models: list[str],
        rows: list[BenchmarkResult],
        sort_by: str,
    ) -> list[str]:
        """Sort model names by the given sort_by strategy."""
        if sort_by == "alphabetical":
            return sorted(models)
        if sort_by == "pass_rate":

            def pass_rate(m: str) -> float:
                model_rows = [r for r in rows if r.model_name == m and r.final_verdict is not None]
                if not model_rows:
                    return -1.0
                return sum(1 for r in model_rows if r.final_verdict == "pass") / len(model_rows)

            return sorted(models, key=pass_rate, reverse=True)

        # default: sort by mean score descending
        def mean_score(m: str) -> float:
            scores = [r.judge_score for r in rows if r.model_name == m and r.judge_score is not None]
            return statistics.mean(scores) if scores else -1.0

        return sorted(models, key=mean_score, reverse=True)

    @override
    def compute_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
        filters: ChartFilters,
    ) -> ChartData:
        """Build heatmap data for task x model cells."""
        rows = results
        if filters.included_models:
            rows = [r for r in rows if r.model_name in filters.included_models]

        if not rows:
            return ChartData(empty_state_message="No data available for heatmap.")

        compact_view = bool(filters.extra.get("compact_view", False))
        sort_by = str(filters.extra.get("sort_by", "score"))
        all_models = list({r.model_name for r in rows})
        sorted_models = self._sort_models(all_models, rows, sort_by)

        if compact_view:
            task_keys = sorted({r.task_category for r in rows})
            cells: dict[tuple[str, str], float | None] = {}
            for task in task_keys:
                for model in sorted_models:
                    model_task_rows = [r for r in rows if r.model_name == model and r.task_category == task]
                    raw = [self._cell_value(r) for r in model_task_rows]
                    vals: list[float] = [v for v in raw if v is not None]
                    cells[(task, model)] = statistics.mean(vals) if vals else None
        else:
            task_keys = sorted({r.task_id for r in rows})
            cells = {}
            for task in task_keys:
                for model in sorted_models:
                    match = next((r for r in rows if r.model_name == model and r.task_id == task), None)
                    cells[(task, model)] = self._cell_value(match) if match else None

        heatmap = HeatmapData(
            row_labels=tuple(task_keys),
            col_labels=tuple(sorted_models),
            cells=cells,
        )
        return ChartData(heatmap=heatmap)


# ---------------------------------------------------------------------------
# Chart 10 — Per-category score breakdown
# ---------------------------------------------------------------------------


class Chart10CategoryBarAggregator(BaseChartAggregator):
    """Grouped bar: avg score or pass rate per model x task category."""

    @override
    def required_filters(self) -> tuple[FilterDescriptor, ...]:
        """Return filter descriptors for model multi-check and score_type combo."""
        return (
            FilterDescriptor(field_id="model_name", label="Models", kind="multi_check"),
            FilterDescriptor(
                field_id="score_type",
                label="Score Type",
                kind="combo",
                options=("avg_score", "pass_rate"),
                default="avg_score",
            ),
        )

    def _cell_score(
        self,
        model: str,
        category: str,
        rows: list[BenchmarkResult],
        score_type: str,
    ) -> float:
        """Compute score for one (model, category) cell; returns -1.0 if no data."""
        cell_rows = [r for r in rows if r.model_name == model and r.task_category == category]
        if not cell_rows:
            return -1.0
        if score_type == "pass_rate":
            verdict_rows = [r for r in cell_rows if r.final_verdict is not None]
            if not verdict_rows:
                return -1.0
            return sum(1 for r in verdict_rows if r.final_verdict == "pass") / len(verdict_rows) * 100.0
        # avg_score
        scored = [r.judge_score for r in cell_rows if r.judge_score is not None]
        return statistics.mean(scored) if scored else -1.0

    @override
    def compute_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
        filters: ChartFilters,
    ) -> ChartData:
        """Compute grouped bar data — one series per model, one group per category."""
        rows = results
        if filters.included_models:
            rows = [r for r in rows if r.model_name in filters.included_models]

        if not rows:
            return ChartData(empty_state_message="No data available.")

        score_type = str(filters.extra.get("score_type", "avg_score"))
        all_models = sorted({r.model_name for r in rows})
        all_categories = sorted({r.task_category for r in rows})

        missing_pairs = 0
        series_data: list[tuple[float, ...]] = []
        for model in all_models:
            cat_scores: list[float] = []
            for cat in all_categories:
                val = self._cell_score(model, cat, rows, score_type)
                if val < 0:
                    missing_pairs += 1
                cat_scores.append(val)
            series_data.append(tuple(cat_scores))

        footnote = f"{missing_pairs} (model, category) pairs had no data (sentinel -1)." if missing_pairs > 0 else ""
        return ChartData(
            series_labels=tuple(all_models),
            category_labels=tuple(all_categories),
            series_data=tuple(series_data),
            footnote=footnote,
        )


# ---------------------------------------------------------------------------
# Chart 11 — Speed vs quality scatter
# ---------------------------------------------------------------------------


class Chart11SpeedQualityAggregator(BaseChartAggregator):
    """Scatter: average tokens/s (speed) vs average judge score (quality) per model."""

    @override
    def required_filters(self) -> tuple[FilterDescriptor, ...]:
        """Return filter descriptors for model multi-check and bubble_size toggle."""
        return (
            FilterDescriptor(field_id="model_name", label="Models", kind="multi_check"),
            FilterDescriptor(field_id="bubble_size", label="Bubble Size", kind="toggle", default=False),
        )

    @override
    def compute_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
        filters: ChartFilters,
    ) -> ChartData:
        """Compute scatter points (avg_tps, avg_score) per model."""
        valid = [
            r
            for r in results
            if r.tokens_per_second is not None
            and r.tokens_per_second > 0
            and r.judge_score is not None
            and not r.has_judge_error
        ]
        if filters.included_models:
            valid = [r for r in valid if r.model_name in filters.included_models]

        if not valid:
            return ChartData(empty_state_message="No speed+quality data available.")

        all_models = sorted({r.model_name for r in valid})
        points: list[tuple[float, float, str]] = []
        counts: dict[str, int] = {}
        for model in all_models:
            model_rows = [r for r in valid if r.model_name == model]
            avg_tps = statistics.mean(_to_float(r.tokens_per_second) for r in model_rows)
            avg_score = statistics.mean(_to_float(r.judge_score) for r in model_rows)
            points.append((avg_tps, avg_score, model))
            counts[model] = len(model_rows)

        return ChartData(
            scatter_points=tuple(points),
            extra={"counts_per_model": counts},
        )


# ---------------------------------------------------------------------------
# Chart 12 — Completion token distribution (boxplot)
# ---------------------------------------------------------------------------


class Chart12BoxplotAggregator(BaseChartAggregator):
    """Boxplot of completion token counts per model."""

    @override
    def required_filters(self) -> tuple[FilterDescriptor, ...]:
        """Return filter descriptor for model multi-check."""
        return (FilterDescriptor(field_id="model_name", label="Models", kind="multi_check"),)

    def _box_set_for(self, values: list[float]) -> tuple[float, float, float, float, float]:
        """Compute five-number summary or mean±stdev fallback for a model's data."""
        if len(values) >= 5:
            sorted_vals = sorted(values)
            q1, _, q3 = statistics.quantiles(values, n=4)[0:3]
            median = statistics.median(values)
            return (sorted_vals[0], q1, median, q3, sorted_vals[-1])
        mean = statistics.mean(values)
        stdev = statistics.stdev(values) if len(values) > 1 else 0.0
        return (
            mean - stdev,
            mean - stdev * 0.5,
            mean,
            mean + stdev * 0.5,
            mean + stdev,
        )

    @override
    def compute_data(
        self,
        *,
        run: BenchmarkRun | None,
        results: list[BenchmarkResult],
        filters: ChartFilters,
    ) -> ChartData:
        """Compute boxplot five-number summaries for completion token counts per model."""
        valid = [r for r in results if r.completion_tokens is not None and not r.has_inference_error]
        if filters.included_models:
            valid = [r for r in valid if r.model_name in filters.included_models]

        if not valid:
            return ChartData(empty_state_message="No completion token data available.")

        grouped = _group_by_model(valid, lambda r: _to_float(r.completion_tokens))
        sorted_models = sorted(grouped)
        box_sets = tuple(self._box_set_for(grouped[m]) for m in sorted_models)

        return ChartData(
            series_labels=tuple(sorted_models),
            box_sets=box_sets,
        )
