"""Pure ``(cache, filters, run context) -> ChartsViewModel`` assembly (STORY-064).

Source of truth: ``docs/v3_specification/05_Result_Widget/tabs/charts_tab.md`` §4.1
(the shared meta line), §5 (global filter chips), §6 (per-chart options), §7
(navigation/dropdown), §11 (empty states). Extracted from ``controller.py`` to keep
that module within the project's lines-per-class limit (coding-style.md). Imports
no Qt symbol -- testable with no ``QApplication``.

**Scope simplification (documented in the story's Notes section):** the Tasks
filter of chart 9 (``HEATMAP_TASK_BY_MODEL``) and the Categories filter of chart 10
(``PER_CATEGORY_BAR``) are not surfaced as extra per-chart option controls here --
chart 10's category narrowing is already available via the shared Category global
filter chip, and chart 9's task-subset narrowing is deferred (out of this story's
acceptance criteria, which cover navigation/filters/drill-down/export/detach, not
every aggregator option's UI surface).
"""

from collections.abc import Callable, Mapping

import msgspec

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkTask,
    ChartData,
    ChartKind,
    HeatmapData,
    RunMode,
)
from ollama_llm_bench.ui.results._internal.charts_tab import mode_policy
from ollama_llm_bench.ui.results._internal.charts_tab.view_state import (
    ChartFilterState,
    ChartsViewState,
    filter_state_for,
    hidden_series_for,
)
from ollama_llm_bench.ui.results.models import (
    ChartOptionControl,
    ChartsViewModel,
    FilterChipDomains,
    FilterChipSelection,
)

__all__: list[str] = ["ChartsSelectionInput", "chip_domains", "select_charts_view_model"]

_CHART_LABELS: dict[ChartKind, str] = {
    ChartKind.AVG_TTFT_PER_MODEL: "Avg TTFT per model",
    ChartKind.AVG_TPS_PER_MODEL: "Avg TPS per model",
    ChartKind.AVG_TIME_PER_MODEL: "Avg time per model",
    ChartKind.SUCCESS_FAILED_INCOMPLETE_STACKED: "Success / Failed / Incomplete",
    ChartKind.PASS_RATE_BY_MODEL: "Pass rate by model",
    ChartKind.AVG_COSINE_BY_MODEL: "Avg Cosine Score by model",
    ChartKind.VERDICT_COUNTS_STACKED: "Verdict counts",
    ChartKind.TIME_VS_TOKENS_SCATTER: "Time vs tokens",
    ChartKind.HEATMAP_TASK_BY_MODEL: "Heatmap (task by model)",
    ChartKind.PER_CATEGORY_BAR: "Per-category bar",
    ChartKind.SPEED_VS_QUALITY_SCATTER: "Speed vs quality",
    ChartKind.TOKENS_PER_TASK_BOX: "Tokens per task (box plot)",
}


class ChartsSelectionInput(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Bundles ``select_charts_view_model``'s inputs to satisfy the project's
    parameter-count limit (coding-style.md); never crosses ``ui/results/``'s own
    boundary, so it lives here rather than in the public ``models.py``."""

    run_mode: RunMode
    view_state: ChartsViewState
    active_kind: ChartKind
    chart_data_cache: Mapping[ChartKind, ChartData | HeatmapData]
    results: tuple[BenchmarkResult, ...]
    tasks_by_id: Mapping[str, BenchmarkTask]
    is_terminal: bool


def chip_domains(
    *, results: tuple[BenchmarkResult, ...], tasks_by_id: Mapping[str, BenchmarkTask]
) -> FilterChipDomains:
    """Compute the five global filter chips' distinct-value domains (charts_tab.md#5).

    Mirrors ``details_tab.select.chip_domains``'s identical unfiltered-source
    policy, narrowed to the Charts tab's five chips (no Tasks/Layer chip).
    """
    seen_models: dict[tuple[str, str], tuple[str, str, str]] = {}
    for result in results:
        key = (result.provider_id, result.model_name)
        if key not in seen_models:
            seen_models[key] = (result.provider_id, result.model_name, result.provider_name)
    return FilterChipDomains(
        models=tuple(seen_models.values()),
        statuses=tuple(dict.fromkeys(result.status.value for result in results)),
        verdicts=tuple(
            dict.fromkeys(
                "ungraded" if result.verdict is None else result.verdict.value for result in results
            )
        ),
        categories=tuple(
            dict.fromkeys(
                tasks_by_id[result.task_id].category
                for result in results
                if result.task_id in tasks_by_id
            )
        ),
        difficulties=tuple(
            dict.fromkeys(
                tasks_by_id[result.task_id].difficulty.value
                for result in results
                if result.task_id in tasks_by_id
            )
        ),
    )


def _filter_selection(filters: ChartFilterState) -> FilterChipSelection:
    return FilterChipSelection(
        models=filters.models,
        statuses=filters.statuses,
        verdicts=filters.verdicts,
        categories=filters.categories,
        difficulties=filters.difficulties,
    )


def _dropdown_entries(
    offered: tuple[ChartKind, ...], chart_data_cache: Mapping[ChartKind, ChartData | HeatmapData]
) -> tuple[tuple[ChartKind, str, bool], ...]:
    return tuple((kind, _CHART_LABELS[kind], _has_data(chart_data_cache, kind)) for kind in offered)


def _outlier_control(*, outlier_exclusion: bool) -> ChartOptionControl:
    return ChartOptionControl(
        key="drop_outliers",
        label="Exclude outliers (IQR x 1.5)",
        kind="toggle",
        value=str(outlier_exclusion).lower(),
    )


def _ttft_options(
    options: dict[str, str], *, outlier_exclusion: bool
) -> tuple[ChartOptionControl, ...]:
    return (
        ChartOptionControl(
            key="unit",
            label="Unit",
            kind="select",
            value=options.get("unit", "ms"),
            choices=("ms", "seconds"),
        ),
        _outlier_control(outlier_exclusion=outlier_exclusion),
    )


def _tps_options(options: dict[str, str], **_kwargs: object) -> tuple[ChartOptionControl, ...]:
    return (
        ChartOptionControl(
            key="aggregation",
            label="Aggregation",
            kind="select",
            value=options.get("aggregation", "mean"),
            choices=("mean", "median"),
        ),
    )


def _time_options(
    options: dict[str, str], *, outlier_exclusion: bool
) -> tuple[ChartOptionControl, ...]:
    return (
        _outlier_control(outlier_exclusion=outlier_exclusion),
        ChartOptionControl(
            key="y_axis_scale",
            label="Y-axis scale",
            kind="select",
            value=options.get("y_axis_scale", "linear"),
            choices=("linear", "log"),
        ),
    )


def _pass_rate_options(
    options: dict[str, str], **_kwargs: object
) -> tuple[ChartOptionControl, ...]:
    return (
        ChartOptionControl(
            key="count_ungraded_as_not_pass",
            label="Count ungraded as not-pass",
            kind="toggle",
            value=options.get("count_ungraded_as_not_pass", "true"),
        ),
    )


def _cosine_options(options: dict[str, str], **_kwargs: object) -> tuple[ChartOptionControl, ...]:
    return (
        ChartOptionControl(
            key="fold_ungraded_as_zero",
            label="Fold ungraded in as 0.0",
            kind="toggle",
            value=options.get("fold_ungraded_as_zero", "false"),
        ),
    )


def _scatter_options(options: dict[str, str], **_kwargs: object) -> tuple[ChartOptionControl, ...]:
    return (
        ChartOptionControl(
            key="x_axis_scale",
            label="X-axis scale",
            kind="select",
            value=options.get("x_axis_scale", "linear"),
            choices=("linear", "log"),
        ),
        ChartOptionControl(
            key="y_axis_scale",
            label="Y-axis scale",
            kind="select",
            value=options.get("y_axis_scale", "linear"),
            choices=("linear", "log"),
        ),
    )


def _heatmap_options(options: dict[str, str], **_kwargs: object) -> tuple[ChartOptionControl, ...]:
    return (
        ChartOptionControl(
            key="cell_value",
            label="Cell value",
            kind="select",
            value=options.get("cell_value", "verdict"),
            choices=("verdict", "cosine"),
        ),
        ChartOptionControl(
            key="group_rows_by_category",
            label="Group rows by category",
            kind="toggle",
            value=options.get("group_rows_by_category", "false"),
        ),
    )


def _per_category_options(
    options: dict[str, str], **_kwargs: object
) -> tuple[ChartOptionControl, ...]:
    return (
        ChartOptionControl(
            key="metric",
            label="Metric",
            kind="select",
            value=options.get("metric", "pass_rate"),
            choices=("pass_rate", "avg_cosine", "avg_time", "avg_tps"),
        ),
    )


def _speed_vs_quality_options(
    options: dict[str, str], **_kwargs: object
) -> tuple[ChartOptionControl, ...]:
    return (
        ChartOptionControl(
            key="y_metric",
            label="Y-axis metric",
            kind="select",
            value=options.get("y_metric", "pass_rate"),
            choices=("pass_rate", "avg_cosine"),
        ),
    )


def _box_options(options: dict[str, str], **_kwargs: object) -> tuple[ChartOptionControl, ...]:
    return (
        ChartOptionControl(
            key="show_outliers",
            label="Show outliers",
            kind="toggle",
            value=options.get("show_outliers", "true"),
        ),
    )


_OPTION_BUILDERS: dict[ChartKind, Callable[..., tuple[ChartOptionControl, ...]]] = {
    ChartKind.AVG_TTFT_PER_MODEL: _ttft_options,
    ChartKind.AVG_TPS_PER_MODEL: _tps_options,
    ChartKind.AVG_TIME_PER_MODEL: _time_options,
    ChartKind.PASS_RATE_BY_MODEL: _pass_rate_options,
    ChartKind.AVG_COSINE_BY_MODEL: _cosine_options,
    ChartKind.TIME_VS_TOKENS_SCATTER: _scatter_options,
    ChartKind.HEATMAP_TASK_BY_MODEL: _heatmap_options,
    ChartKind.PER_CATEGORY_BAR: _per_category_options,
    ChartKind.SPEED_VS_QUALITY_SCATTER: _speed_vs_quality_options,
    ChartKind.TOKENS_PER_TASK_BOX: _box_options,
}


def _option_controls(
    chart_kind: ChartKind, filters: ChartFilterState, *, outlier_exclusion: bool
) -> tuple[ChartOptionControl, ...]:
    builder = _OPTION_BUILDERS.get(chart_kind)
    if builder is None:
        return ()
    return builder(filters.options, outlier_exclusion=outlier_exclusion)


def _aggregation_label(chart_kind: ChartKind, filters: ChartFilterState) -> str:
    if chart_kind is ChartKind.AVG_TPS_PER_MODEL:
        return filters.options.get("aggregation", "mean")
    return "mean"


def _clear_filters_enabled(filters: ChartFilterState) -> bool:
    return bool(
        filters.models
        or filters.statuses
        or filters.verdicts
        or filters.categories
        or filters.difficulties
        or filters.options
    )


def _has_data(
    chart_data_cache: Mapping[ChartKind, ChartData | HeatmapData], kind: ChartKind
) -> bool:
    data = chart_data_cache.get(kind)
    return data is not None and data.empty_state_message is None


def select_charts_view_model(inputs: ChartsSelectionInput) -> ChartsViewModel:
    """Assemble the Charts tab's full render state for the active chart.

    Args:
        inputs: The bundled selection inputs -- run mode, current view state,
            active chart kind, every mode-offered chart's prepared data (fetched
            once per recompute by ``ChartsTabController``), the run's results/
            tasks for the filter-chip domains, and the run's terminal-state flag.

    Returns:
        The full ``ChartsViewModel`` to push to the bound view.
    """
    offered = mode_policy.offered_chart_kinds(inputs.run_mode)
    active_index = offered.index(inputs.active_kind)
    data = inputs.chart_data_cache.get(inputs.active_kind)
    has_data = data is not None and data.empty_state_message is None
    filters = filter_state_for(inputs.view_state, inputs.active_kind)
    aggregation = _aggregation_label(inputs.active_kind, filters)
    meta_line = (
        f"Aggregation: {aggregation} · Mode: {inputs.run_mode.value} · "
        f"{active_index + 1} / {len(offered)}"
    )

    def _cache_has_data(kind: ChartKind) -> bool:
        return _has_data(inputs.chart_data_cache, kind)

    return ChartsViewModel(
        chart_kind=inputs.active_kind,
        chart_index=active_index,
        chart_count=len(offered),
        prev_enabled=mode_policy.prev_navigable_index(
            current_index=active_index, offered=offered, has_data=_cache_has_data
        )
        is not None,
        next_enabled=mode_policy.next_navigable_index(
            current_index=active_index, offered=offered, has_data=_cache_has_data
        )
        is not None,
        dropdown_entries=_dropdown_entries(offered, inputs.chart_data_cache),
        chart_data=data if has_data and isinstance(data, ChartData) else None,
        heatmap_data=data if has_data and isinstance(data, HeatmapData) else None,
        empty_state_message=None
        if has_data
        else (data.empty_state_message if data is not None else None),
        meta_line=meta_line,
        filter_domains=chip_domains(results=inputs.results, tasks_by_id=inputs.tasks_by_id),
        filter_selection=_filter_selection(filters),
        verdict_filter_visible=inputs.run_mode is RunMode.GRADED,
        option_controls=_option_controls(
            inputs.active_kind, filters, outlier_exclusion=inputs.view_state.outlier_exclusion
        ),
        hidden_series=hidden_series_for(inputs.view_state, inputs.active_kind),
        clear_filters_enabled=_clear_filters_enabled(filters),
        detach_enabled=True,
        export_enabled=inputs.is_terminal,
    )
