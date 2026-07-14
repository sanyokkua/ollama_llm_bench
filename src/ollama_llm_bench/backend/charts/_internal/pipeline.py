"""The shared five-step pipeline every aggregator runs (`13_CHART_AGGREGATORS.md` §6).

Mode gate (§6.1), the five global filters (§6.2), the per-chart `COMPLETED`-status
pre-filter (§6.3), per-chart option resolution (§6.4), and the grouping/ordering
helpers used by step 5 (§6.5) plus the minimum-sample-size guard (§6.5a).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

import structlog

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkTask,
    ChartData,
    ChartFilters,
    ChartKind,
    HeatmapData,
    ModelDescriptor,
    ResultStatus,
    TaskId,
    Verdict,
)

log = structlog.get_logger(__name__)

UNGRADED_TOKEN: Final[str] = "ungraded"  # noqa: S105  # a filter-domain token, not a credential
"""The `ChartFilters.verdicts` token selecting rows with `verdict is None` (§6.2)."""

MODE_GATE_MESSAGE: Final[str] = "This chart is available only for graded runs."
"""The empty-state message for a grading chart requested in a non-`GRADED` run (§6.1)."""

GRADING_KINDS: Final[frozenset[ChartKind]] = frozenset(
    {
        ChartKind.PASS_RATE_BY_MODEL,
        ChartKind.AVG_COSINE_BY_MODEL,
        ChartKind.VERDICT_COUNTS_STACKED,
        ChartKind.HEATMAP_TASK_BY_MODEL,
        ChartKind.PER_CATEGORY_BAR,
        ChartKind.SPEED_VS_QUALITY_SCATTER,
    }
)
"""The six chart kinds offered only for `RunMode.GRADED` (§7.13)."""

_KEEP_ALL_STATUS_KINDS: Final[frozenset[ChartKind]] = frozenset(
    {ChartKind.SUCCESS_FAILED_INCOMPLETE_STACKED}
)
"""The one chart kind whose per-chart status pre-filter keeps every surviving row (§6.3)."""


def is_grading_chart(chart_kind: ChartKind) -> bool:
    """Return whether `chart_kind` is one of the six grading-only kinds (§7.13)."""
    return chart_kind in GRADING_KINDS


def empty_chart_data(chart_kind: ChartKind, *, message: str) -> ChartData:
    """Build a non-heatmap kind's empty-state `ChartData` (§6.7, §9).

    Args:
        chart_kind: Any kind except `HEATMAP_TASK_BY_MODEL`.
        message: The kind-specific empty-state message from §7's catalog.
    """
    return ChartData(chart_kind=chart_kind, categories=(), series=(), empty_state_message=message)


def empty_heatmap_data(*, message: str) -> HeatmapData:
    """Build the empty-state `HeatmapData` for `HEATMAP_TASK_BY_MODEL` (§6.7, §9)."""
    return HeatmapData(row_labels=(), column_labels=(), cells=(), empty_state_message=message)


def empty_chart_for(chart_kind: ChartKind, *, message: str) -> ChartData | HeatmapData:
    """Build the kind-specific empty-state structure carrying `message` (§6.7, §9).

    Args:
        chart_kind: The chart kind whose empty state is being built.
        message: The kind-specific empty-state message from §7's catalog.

    Returns:
        A `HeatmapData` for `HEATMAP_TASK_BY_MODEL`, a `ChartData` for every
        other kind, both with empty series/cells and `empty_state_message` set.
    """
    if chart_kind == ChartKind.HEATMAP_TASK_BY_MODEL:
        return empty_heatmap_data(message=message)
    return empty_chart_data(chart_kind, message=message)


def index_tasks_by_id(tasks: tuple[BenchmarkTask, ...]) -> dict[TaskId, BenchmarkTask]:
    """Build the `task_id -> BenchmarkTask` lookup used by the join in §6.2."""
    return {task.task_id: task for task in tasks}


def _verdict_selection_matches(verdict: Verdict | None, selection: tuple[str, ...]) -> bool:
    if verdict is None:
        return UNGRADED_TOKEN in selection
    return verdict.value in selection


def apply_global_filters(
    *,
    results: tuple[BenchmarkResult, ...],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    filters: ChartFilters,
) -> tuple[BenchmarkResult, ...]:
    """Apply the five global filters plus the task-join drop (§6.2, CA-25..CA-28).

    A row whose `task_id` has no matching task is dropped unconditionally (it
    cannot be classified for the Category/Difficulty filters). Each of the five
    filters keeps every row when its selection is empty ("all").
    """
    selected_models = {(m.provider_id, m.model_name) for m in filters.models}
    kept: list[BenchmarkResult] = []
    for row in results:
        task = tasks_by_id.get(row.task_id)
        if task is None:
            continue
        if selected_models and (row.provider_id, row.model_name) not in selected_models:
            continue
        if filters.statuses and row.status not in filters.statuses:
            continue
        if filters.verdicts and not _verdict_selection_matches(row.verdict, filters.verdicts):
            continue
        if filters.categories and task.category not in filters.categories:
            continue
        if filters.difficulties and task.difficulty not in filters.difficulties:
            continue
        kept.append(row)
    return tuple(kept)


def apply_status_prefilter(
    results: tuple[BenchmarkResult, ...], chart_kind: ChartKind
) -> tuple[BenchmarkResult, ...]:
    """Apply the per-chart `COMPLETED`-status pre-filter (§6.3).

    `SUCCESS_FAILED_INCOMPLETE_STACKED` keeps every row; every other kind keeps
    only `status == COMPLETED` rows.
    """
    if chart_kind in _KEEP_ALL_STATUS_KINDS:
        return results
    return tuple(row for row in results if row.status == ResultStatus.COMPLETED)


def read_bool_option(
    filters: ChartFilters, *, key: str, default: bool, chart_kind: ChartKind
) -> bool:
    """Read a boolean per-chart option, substituting `default` on an out-of-domain
    or absent value (§6.4, §9); an out-of-domain (present but non-bool) value is
    logged once at warning level."""
    if key not in filters.options:
        return default
    value = filters.options[key]
    if isinstance(value, bool):
        return value
    _log_out_of_domain(chart_kind=chart_kind, option_name=key, invalid_value=value)
    return default


def read_enum_option(
    filters: ChartFilters,
    *,
    key: str,
    domain: tuple[str, ...],
    default: str,
    chart_kind: ChartKind,
) -> str:
    """Read a string-domain per-chart option, substituting `default` on an
    out-of-domain or absent value (§6.4, §9); an out-of-domain value is logged
    once at warning level."""
    if key not in filters.options:
        return default
    value = filters.options[key]
    if isinstance(value, str) and value in domain:
        return value
    _log_out_of_domain(chart_kind=chart_kind, option_name=key, invalid_value=value)
    return default


def _log_out_of_domain(
    *, chart_kind: ChartKind, option_name: str, invalid_value: str | bool
) -> None:
    log.warning(
        "chart_option_out_of_domain",
        chart_kind=chart_kind.value,
        option_name=option_name,
        invalid_value=str(invalid_value),
    )


@dataclass(slots=True, frozen=True)
class ModelGroup:
    """One `(provider_id, model_name)` group of rows, stably ordered (§6.5)."""

    descriptor: ModelDescriptor
    label: str
    rows: tuple[BenchmarkResult, ...]


def model_label(row: BenchmarkResult) -> str:
    """Return the display label for `row`'s model — snapshot `provider_name`, never
    the internal `provider_id` (DD-33)."""
    return f"{row.provider_name} / {row.model_name}"


def group_by_model(rows: tuple[BenchmarkResult, ...]) -> tuple[ModelGroup, ...]:
    """Group `rows` by `(provider_id, model_name)`, ordered ascending by
    `provider_id` then `model_name` (§6.5)."""
    buckets: dict[tuple[str, str], list[BenchmarkResult]] = {}
    labels: dict[tuple[str, str], str] = {}
    for row in rows:
        key = (row.provider_id, row.model_name)
        buckets.setdefault(key, []).append(row)
        labels.setdefault(key, model_label(row))
    return tuple(
        ModelGroup(
            descriptor=ModelDescriptor(provider_id=key[0], model_name=key[1]),
            label=labels[key],
            rows=tuple(buckets[key]),
        )
        for key in sorted(buckets)
    )


@dataclass(slots=True, frozen=True)
class CategoryModelGroup:
    """One `(category, provider_id, model_name)` group of rows (§6.5, kind 10)."""

    category: str
    descriptor: ModelDescriptor
    label: str
    rows: tuple[BenchmarkResult, ...]


def group_by_category_and_model(
    rows: tuple[BenchmarkResult, ...], tasks_by_id: Mapping[TaskId, BenchmarkTask]
) -> tuple[CategoryModelGroup, ...]:
    """Group `rows` by `(category, provider_id, model_name)` for `PER_CATEGORY_BAR`
    (§6.5, §7.10). A row whose task has an empty `category` is excluded."""
    buckets: dict[tuple[str, str, str], list[BenchmarkResult]] = {}
    labels: dict[tuple[str, str, str], str] = {}
    for row in rows:
        task = tasks_by_id.get(row.task_id)
        if task is None or not task.category:
            continue
        key = (task.category, row.provider_id, row.model_name)
        buckets.setdefault(key, []).append(row)
        labels.setdefault(key, model_label(row))
    return tuple(
        CategoryModelGroup(
            category=key[0],
            descriptor=ModelDescriptor(provider_id=key[1], model_name=key[2]),
            label=labels[key],
            rows=tuple(buckets[key]),
        )
        for key in sorted(buckets)
    )


def sample_flag(n: int, min_sample_size: int) -> bool:
    """Return whether a group's sample size `n` is below `min_sample_size` (§6.5a)."""
    return n < min_sample_size
