"""`HEATMAP_TASK_BY_MODEL` — kind 9 (`13_CHART_AGGREGATORS.md` §7.9)."""

from collections.abc import Mapping

from ollama_llm_bench.backend.charts._internal import pipeline
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkTask,
    ChartFilters,
    ChartKind,
    HeatmapData,
    TaskId,
    Verdict,
)

_EMPTY_MESSAGE = "The heatmap needs at least one completed task per model."
_CELL_VALUE_DOMAIN = ("verdict", "cosine")


def compute_heatmap_task_by_model(
    *,
    rows: tuple[BenchmarkResult, ...],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    filters: ChartFilters,
    min_sample_size: int,
) -> HeatmapData:
    """Row = `task_id`, column = `(provider_id, model_name)` cell matrix (§7.9, CA-17, CA-18).

    Cell-level, so no minimum-sample-size guard applies (§6.5a).
    """
    del min_sample_size
    cell_value = pipeline.read_enum_option(
        filters,
        key="cell_value",
        domain=_CELL_VALUE_DOMAIN,
        default="verdict",
        chart_kind=ChartKind.HEATMAP_TASK_BY_MODEL,
    )
    group_by_category = pipeline.read_bool_option(
        filters,
        key="group_rows_by_category",
        default=False,
        chart_kind=ChartKind.HEATMAP_TASK_BY_MODEL,
    )
    tasks_filter = _tasks_filter(filters)

    if not rows:
        return HeatmapData(
            row_labels=(), column_labels=(), cells=(), empty_state_message=_EMPTY_MESSAGE
        )

    row_tasks = _ordered_row_tasks(tasks_by_id, tasks_filter, group_by_category=group_by_category)
    columns = pipeline.group_by_model(rows)
    column_labels = tuple(group.descriptor for group in columns)

    cell_lookup = {(row.task_id, row.provider_id, row.model_name): row for row in rows}
    cells = tuple(
        tuple(
            _cell_value(
                cell_lookup.get((task.task_id, col.provider_id, col.model_name)), cell_value
            )
            for col in column_labels
        )
        for task in row_tasks
    )
    if not any(value is not None for cell_row in cells for value in cell_row):
        return HeatmapData(
            row_labels=(), column_labels=(), cells=(), empty_state_message=_EMPTY_MESSAGE
        )

    return HeatmapData(
        row_labels=tuple(task.task_id for task in row_tasks),
        column_labels=tuple(f"{group.label}" for group in columns),
        cells=cells,
    )


def _tasks_filter(filters: ChartFilters) -> frozenset[TaskId] | None:
    raw = filters.options.get("tasks")
    if isinstance(raw, str) and raw:
        return frozenset(raw.split(","))
    return None


def _ordered_row_tasks(
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    tasks_filter: frozenset[TaskId] | None,
    *,
    group_by_category: bool,
) -> tuple[BenchmarkTask, ...]:
    tasks = [
        task
        for task in tasks_by_id.values()
        if tasks_filter is None or task.task_id in tasks_filter
    ]
    if group_by_category:
        tasks.sort(key=lambda task: (task.category, task.task_order))
    else:
        tasks.sort(key=lambda task: task.task_order)
    return tuple(tasks)


def _cell_value(row: BenchmarkResult | None, cell_value: str) -> float | None:
    if row is None:
        return None
    if cell_value == "cosine":
        return row.cosine_similarity
    if row.verdict is None:
        return None
    return 1.0 if row.verdict == Verdict.PASS else 0.0
