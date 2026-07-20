"""Pure row-mapping, filtering, and formatting logic for the Result widget's Details tab.

Imports no Qt symbol — testable with no QApplication.
"""

from collections.abc import Callable
from enum import StrEnum
from typing import Final

import msgspec
import msgspec.json

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkTask,
    Difficulty,
    ResolutionLayer,
    ResultStatus,
    RunMode,
    Verdict,
)
from ollama_llm_bench.ui.results.models import (
    AttemptRow,
    ChartDrilldownRequest,
    DetailRowViewModel,
    DetailsViewModel,
    PhaseEvaluationRow,
    ResultDetailViewModel,
)

_EM_DASH: Final[str] = "—"


class DetailsColumnKey(StrEnum):
    """The 24 Details-tab columns, in their master display order (details_tab.md#3)."""

    PROVIDER_MODEL = "provider_model"
    TASK = "task"
    CATEGORY = "category"
    SUB_CATEGORY = "sub_category"
    DIFFICULTY = "difficulty"
    TYPE = "type"
    STATUS = "status"
    TIME_MS = "time_ms"
    TTFT_MS = "ttft_ms"
    PROMPT_TOKENS = "prompt_tokens"
    TOKENS = "tokens"
    TPS = "tps"
    SANITY_CHECK = "sanity_check"
    KEYWORD = "keyword"
    COSINE_SCORE = "cosine_score"
    COSINE_VERDICT = "cosine_verdict"
    JUDGE = "judge"
    LAYER = "layer"
    VERDICT = "verdict"
    REASON = "reason"
    ERROR = "error"
    ATTEMPTS = "attempts"
    STARTED_AT = "started_at"
    FINISHED_AT = "finished_at"


_COLUMN_ORDER: Final[tuple[DetailsColumnKey, ...]] = tuple(DetailsColumnKey)

_COLUMN_LABELS: Final[dict[DetailsColumnKey, str]] = {
    DetailsColumnKey.PROVIDER_MODEL: "Provider / Model",
    DetailsColumnKey.TASK: "Task",
    DetailsColumnKey.CATEGORY: "Category",
    DetailsColumnKey.SUB_CATEGORY: "Sub-category",
    DetailsColumnKey.DIFFICULTY: "Difficulty",
    DetailsColumnKey.TYPE: "Type",
    DetailsColumnKey.STATUS: "Status",
    DetailsColumnKey.TIME_MS: "Time (ms)",
    DetailsColumnKey.TTFT_MS: "TTFT (ms)",
    DetailsColumnKey.PROMPT_TOKENS: "Prompt tokens",
    DetailsColumnKey.TOKENS: "Tokens",
    DetailsColumnKey.TPS: "TPS",
    DetailsColumnKey.SANITY_CHECK: "Sanity check",
    DetailsColumnKey.KEYWORD: "Keyword",
    DetailsColumnKey.COSINE_SCORE: "Cosine Score",
    DetailsColumnKey.COSINE_VERDICT: "Cosine verdict",
    DetailsColumnKey.JUDGE: "Judge",
    DetailsColumnKey.LAYER: "Layer",
    DetailsColumnKey.VERDICT: "Verdict",
    DetailsColumnKey.REASON: "Reason",
    DetailsColumnKey.ERROR: "Error",
    DetailsColumnKey.ATTEMPTS: "Attempts",
    DetailsColumnKey.STARTED_AT: "Started at",
    DetailsColumnKey.FINISHED_AT: "Finished at",
}

_GRADED_ONLY_COLUMNS: Final[frozenset[DetailsColumnKey]] = frozenset(
    {
        DetailsColumnKey.SANITY_CHECK,
        DetailsColumnKey.KEYWORD,
        DetailsColumnKey.COSINE_SCORE,
        DetailsColumnKey.COSINE_VERDICT,
        DetailsColumnKey.JUDGE,
        DetailsColumnKey.LAYER,
        DetailsColumnKey.VERDICT,
        DetailsColumnKey.REASON,
    }
)

_DEFAULT_VISIBLE_COLUMNS: Final[frozenset[DetailsColumnKey]] = frozenset(
    {
        DetailsColumnKey.PROVIDER_MODEL,
        DetailsColumnKey.TASK,
        DetailsColumnKey.CATEGORY,
        DetailsColumnKey.STATUS,
        DetailsColumnKey.TIME_MS,
        DetailsColumnKey.TTFT_MS,
        DetailsColumnKey.TOKENS,
        DetailsColumnKey.TPS,
        DetailsColumnKey.COSINE_SCORE,
        DetailsColumnKey.LAYER,
        DetailsColumnKey.VERDICT,
    }
)


def offered_columns(run_mode: RunMode) -> tuple[DetailsColumnKey, ...]:
    """Return the columns the given run mode offers (details_tab.md#4).

    Args:
        run_mode: The selected run's mode.

    Returns:
        The offered columns in master display order. ``GRADED`` offers all 24;
        ``SYNTHETIC`` and ``TASKS`` drop the eight grading-only columns.
    """
    if run_mode == RunMode.GRADED:
        return _COLUMN_ORDER
    return tuple(c for c in _COLUMN_ORDER if c not in _GRADED_ONLY_COLUMNS)


def default_visible_columns(run_mode: RunMode) -> frozenset[DetailsColumnKey]:
    """Return the mode's default-visible column subset.

    Args:
        run_mode: The selected run's mode.

    Returns:
        The default-visible columns (details_tab.md#3), intersected with what
        the mode offers (details_tab.md#4).
    """
    offered = set(offered_columns(run_mode))
    return frozenset(_DEFAULT_VISIBLE_COLUMNS & offered)


def column_label(column: DetailsColumnKey) -> str:
    """Return the display label for one column.

    Args:
        column: The column to label.

    Returns:
        The column's display header text (details_tab.md#3).
    """
    return _COLUMN_LABELS[column]


class DetailsModelKey(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The composite ``(provider_id, model_name)`` grouping key.

    Carries the display snapshot ``provider_name`` alongside the grouping fields
    so the Models chip can render a label without a second lookup (DD-33).
    """

    provider_id: str
    model_name: str
    provider_name: str


class DetailsChipDomains(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The distinct-value domain for each of the seven filter chips (details_tab.md#5)."""

    models: tuple[DetailsModelKey, ...]
    tasks: tuple[str, ...]
    categories: tuple[str, ...]
    statuses: tuple[ResultStatus, ...]
    verdicts: tuple[Verdict | None, ...]
    layers: tuple[ResolutionLayer | None, ...]
    difficulties: tuple[Difficulty, ...]


_TERMINAL_FAILURE_STATUSES: Final[frozenset[ResultStatus]] = frozenset(
    {
        ResultStatus.FAILED_INFERENCE,
        ResultStatus.FAILED_PROVIDER,
        ResultStatus.FAILED_TIMEOUT,
        ResultStatus.FAILED_JUDGE_TIMEOUT,
        ResultStatus.ERRORED,
    }
)


def badge_role_for_verdict(verdict: Verdict | None) -> str:
    """Return the colour role for a verdict-family cell (details_tab.md#11).

    Args:
        verdict: The verdict value, or None if unavailable.

    Returns:
        The badge role: "success" for PASS, "error" for FAIL, "muted" for None.
    """
    if verdict is None:
        return "muted"
    return "success" if verdict == Verdict.PASS else "error"


def badge_role_for_status(status: ResultStatus) -> str:
    """Return the colour role for the Status cell (details_tab.md#11).

    Args:
        status: The result status.

    Returns:
        The badge role: "success" for COMPLETED, "error" for terminal failures,
        "info" for in-progress states.
    """
    if status == ResultStatus.COMPLETED:
        return "success"
    if status in _TERMINAL_FAILURE_STATUSES:
        return "error"
    return "info"


def badge_role_for_layer(layer: ResolutionLayer | None) -> str:
    """Return the colour role for the Layer cell (details_tab.md#11).

    Args:
        layer: The resolution layer, or None if unavailable.

    Returns:
        The badge role: "info" for KEYWORD, COSINE, JUDGE; "muted" for SKIP or None.
    """
    if layer is None or layer == ResolutionLayer.SKIP:
        return "muted"
    return "info"


def chip_domains(
    *, results: tuple[BenchmarkResult, ...], tasks_by_id: dict[str, BenchmarkTask]
) -> DetailsChipDomains:
    """Compute the seven chips' distinct-value domains from the run's current results.

    Args:
        results: The run's current result rows, in arbitrary order.
        tasks_by_id: The run's frozen tasks, keyed by ``task_id``, for the
            Category/Difficulty chips that are joined from ``BenchmarkTask``.

    Returns:
        The distinct values each filter chip offers (details_tab.md#5).
    """
    seen_models: dict[tuple[str, str], DetailsModelKey] = {}
    for result in results:
        key = (result.provider_id, result.model_name)
        if key not in seen_models:
            seen_models[key] = DetailsModelKey(
                provider_id=result.provider_id,
                model_name=result.model_name,
                provider_name=result.provider_name,
            )
    return DetailsChipDomains(
        models=tuple(seen_models.values()),
        tasks=tuple(dict.fromkeys(result.task_id for result in results)),
        categories=tuple(
            dict.fromkeys(
                tasks_by_id[result.task_id].category
                for result in results
                if result.task_id in tasks_by_id
            )
        ),
        statuses=tuple(dict.fromkeys(result.status for result in results)),
        verdicts=tuple(dict.fromkeys(result.verdict for result in results)),
        layers=tuple(dict.fromkeys(result.resolution_layer for result in results)),
        difficulties=tuple(
            dict.fromkeys(
                tasks_by_id[result.task_id].difficulty
                for result in results
                if result.task_id in tasks_by_id
            )
        ),
    )


class ColumnFilterEntry(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One per-column filter: the set of values still allowed through for that column."""

    column: DetailsColumnKey
    allowed_values: tuple[str, ...]


class DetailsFilters(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The seven filter-bar chips' current selections (details_tab.md#5). Empty means 'all'."""

    models: tuple[tuple[str, str], ...] = ()
    tasks: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    statuses: tuple[ResultStatus, ...] = ()
    verdicts: tuple[Verdict | None, ...] = ()
    layers: tuple[ResolutionLayer | None, ...] = ()
    difficulties: tuple[Difficulty, ...] = ()
    column_filters: tuple[ColumnFilterEntry, ...] = ()

    def is_default(self) -> bool:
        """True when every chip and every per-column filter is at 'all selected'."""
        return not any(
            (
                self.models,
                self.tasks,
                self.categories,
                self.statuses,
                self.verdicts,
                self.layers,
                self.difficulties,
                self.column_filters,
            )
        )


class DetailsColumnLayout(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Column visibility and order (details_tab.md#7). PROVIDER_MODEL is always first."""

    visible: tuple[DetailsColumnKey, ...]
    order: tuple[DetailsColumnKey, ...]


class DetailsSort(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The active sort (details_tab.md#8). `column=None` means no sort (insertion order)."""

    column: DetailsColumnKey | None
    descending: bool


class DetailsViewState(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Details tab's full persisted per-run view state (details_tab.md#15)."""

    filters: DetailsFilters
    columns: DetailsColumnLayout
    sort: DetailsSort


def default_view_state(run_mode: RunMode) -> DetailsViewState:
    """The built-in default: all filters selected, mode's default columns, Time-descending sort."""
    offered = offered_columns(run_mode)
    visible = tuple(c for c in offered if c in default_visible_columns(run_mode))
    return DetailsViewState(
        filters=DetailsFilters(),
        columns=DetailsColumnLayout(visible=visible, order=offered),
        sort=DetailsSort(column=DetailsColumnKey.TIME_MS, descending=True),
    )


def apply_drilldown(state: DetailsViewState, request: ChartDrilldownRequest) -> DetailsViewState:
    """Apply a chart-click drill-down on top of the current view state (details_tab.md#10).

    Replaces the Models/Tasks/Status/Verdict chips the request narrows; every other
    filter and the column/sort layout are left untouched. Per DT-EC-2, the drill-down
    filter replaces any conflicting chip rather than composing with it.
    """
    models = state.filters.models
    if request.provider_id is not None and request.model_name is not None:
        models = ((request.provider_id, request.model_name),)
    tasks = state.filters.tasks
    if request.task_id is not None:
        tasks = (request.task_id,)
    statuses = state.filters.statuses
    if request.status is not None:
        statuses = (ResultStatus(request.status),)
    verdicts = state.filters.verdicts
    if request.verdict is not None:
        verdicts = (Verdict(request.verdict),)
    new_filters = msgspec.structs.replace(
        state.filters, models=models, tasks=tasks, statuses=statuses, verdicts=verdicts
    )
    return msgspec.structs.replace(state, filters=new_filters)


def encode_view_state(state: DetailsViewState) -> str:
    """Serialize a view state to the string persisted via ResultGateway.set_setting."""
    return msgspec.json.encode(state).decode("utf-8")


def decode_view_state(raw: str) -> DetailsViewState:
    """Deserialize a view state previously produced by encode_view_state."""
    return msgspec.json.decode(raw.encode("utf-8"), type=DetailsViewState)


def _format_optional_int(value: int | None) -> str:
    """Format an optional-integer cell, using the em-dash convention for None."""
    return _EM_DASH if value is None else str(value)


def _format_tps(result: BenchmarkResult) -> str:
    """Format the Tokens-per-second cell, prefixing an estimated value with '≈'."""
    if result.tokens_per_second is None:
        return _EM_DASH
    formatted = f"{result.tokens_per_second:.2f}"
    return f"≈{formatted}" if result.tokens_estimated else formatted


def _format_cosine_score(result: BenchmarkResult, score_display_format: str) -> str:
    """Format the Cosine Score cell as a decimal or a percentage, per the run's display setting."""
    if result.cosine_similarity is None:
        return _EM_DASH
    if score_display_format == "percentage":
        return f"{result.cosine_similarity * 100:.1f}%"
    return f"{result.cosine_similarity:.2f}"


def _format_verdict(value: Verdict | None) -> str:
    """Format a verdict-family value as PASS/FAIL, or an em-dash when unavailable."""
    if value is None:
        return _EM_DASH
    return "PASS" if value == Verdict.PASS else "FAIL"


_TASK_STR_EXTRACTORS: Final[dict[DetailsColumnKey, Callable[[BenchmarkTask], str]]] = {
    DetailsColumnKey.CATEGORY: lambda task: task.category,
    DetailsColumnKey.SUB_CATEGORY: lambda task: task.sub_category,
    DetailsColumnKey.DIFFICULTY: lambda task: task.difficulty.value,
    DetailsColumnKey.TYPE: lambda task: task.task_origin.value,
}


def _format_task_attr(column: DetailsColumnKey, task: BenchmarkTask | None) -> str:
    """Format a task-derived column (Category/Sub-category/Difficulty/Type).

    Args:
        column: One of the four task-derived columns above.
        task: The joined task, or None when the run's task set no longer has it.

    Returns:
        The task's value for that column, or an em-dash when the task is unknown.
    """
    if task is None:
        return _EM_DASH
    return _TASK_STR_EXTRACTORS[column](task)


_VERDICT_FIELD_GETTERS: Final[
    dict[DetailsColumnKey, Callable[[BenchmarkResult], Verdict | None]]
] = {
    DetailsColumnKey.KEYWORD: lambda result: result.keyword_verdict,
    DetailsColumnKey.COSINE_VERDICT: lambda result: result.cosine_verdict,
    DetailsColumnKey.JUDGE: lambda result: result.judge_verdict,
    DetailsColumnKey.VERDICT: lambda result: result.verdict,
}


def _format_verdict_column(column: DetailsColumnKey, result: BenchmarkResult) -> str:
    """Format one of the four verdict-family columns via the shared PASS/FAIL/em-dash rule."""
    return _format_verdict(_VERDICT_FIELD_GETTERS[column](result))


_OPTIONAL_INT_GETTERS: Final[dict[DetailsColumnKey, Callable[[BenchmarkResult], int | None]]] = {
    DetailsColumnKey.TIME_MS: lambda result: result.total_time_ms,
    DetailsColumnKey.TTFT_MS: lambda result: result.ttft_ms,
    DetailsColumnKey.PROMPT_TOKENS: lambda result: result.prompt_tokens,
    DetailsColumnKey.TOKENS: lambda result: result.completion_tokens,
}


def _format_optional_int_column(column: DetailsColumnKey, result: BenchmarkResult) -> str:
    """Format one of the four optional-integer columns (Time/TTFT/Prompt tokens/Tokens)."""
    return _format_optional_int(_OPTIONAL_INT_GETTERS[column](result))


def _format_sanity_check(result: BenchmarkResult) -> str:
    """Format the Sanity check cell as ok/failed, or an em-dash when not evaluated."""
    if result.sanity_check_passed is None:
        return _EM_DASH
    return "ok" if result.sanity_check_passed else "failed"


def _format_layer(result: BenchmarkResult) -> str:
    """Format the Layer cell, or an em-dash when no layer resolved the verdict."""
    if result.resolution_layer is None:
        return _EM_DASH
    return result.resolution_layer.value


def _format_first_line_or_dash(value: str | None) -> str:
    """Format a free-text cell (Reason/Error) as its first line, or an em-dash when absent."""
    return (value or _EM_DASH).splitlines()[0]


_CELL_FORMATTERS: Final[
    dict[DetailsColumnKey, Callable[[BenchmarkResult, BenchmarkTask | None, str], str]]
] = {
    DetailsColumnKey.PROVIDER_MODEL: (
        lambda result, _task, _score_format: f"{result.provider_name} / {result.model_name}"
    ),
    DetailsColumnKey.TASK: lambda result, _task, _score_format: result.task_id,
    DetailsColumnKey.CATEGORY: (
        lambda _result, task, _score_format: _format_task_attr(DetailsColumnKey.CATEGORY, task)
    ),
    DetailsColumnKey.SUB_CATEGORY: (
        lambda _result, task, _score_format: _format_task_attr(DetailsColumnKey.SUB_CATEGORY, task)
    ),
    DetailsColumnKey.DIFFICULTY: (
        lambda _result, task, _score_format: _format_task_attr(DetailsColumnKey.DIFFICULTY, task)
    ),
    DetailsColumnKey.TYPE: (
        lambda _result, task, _score_format: _format_task_attr(DetailsColumnKey.TYPE, task)
    ),
    DetailsColumnKey.STATUS: lambda result, _task, _score_format: result.status.value,
    DetailsColumnKey.TIME_MS: (
        lambda result, _task, _score_format: _format_optional_int_column(
            DetailsColumnKey.TIME_MS, result
        )
    ),
    DetailsColumnKey.TTFT_MS: (
        lambda result, _task, _score_format: _format_optional_int_column(
            DetailsColumnKey.TTFT_MS, result
        )
    ),
    DetailsColumnKey.PROMPT_TOKENS: (
        lambda result, _task, _score_format: _format_optional_int_column(
            DetailsColumnKey.PROMPT_TOKENS, result
        )
    ),
    DetailsColumnKey.TOKENS: (
        lambda result, _task, _score_format: _format_optional_int_column(
            DetailsColumnKey.TOKENS, result
        )
    ),
    DetailsColumnKey.TPS: lambda result, _task, _score_format: _format_tps(result),
    DetailsColumnKey.SANITY_CHECK: lambda result, _task, _score_format: _format_sanity_check(
        result
    ),
    DetailsColumnKey.KEYWORD: (
        lambda result, _task, _score_format: _format_verdict_column(
            DetailsColumnKey.KEYWORD, result
        )
    ),
    DetailsColumnKey.COSINE_SCORE: (
        lambda result, _task, score_format: _format_cosine_score(result, score_format)
    ),
    DetailsColumnKey.COSINE_VERDICT: (
        lambda result, _task, _score_format: _format_verdict_column(
            DetailsColumnKey.COSINE_VERDICT, result
        )
    ),
    DetailsColumnKey.JUDGE: (
        lambda result, _task, _score_format: _format_verdict_column(DetailsColumnKey.JUDGE, result)
    ),
    DetailsColumnKey.LAYER: lambda result, _task, _score_format: _format_layer(result),
    DetailsColumnKey.VERDICT: (
        lambda result, _task, _score_format: _format_verdict_column(
            DetailsColumnKey.VERDICT, result
        )
    ),
    DetailsColumnKey.REASON: (
        lambda result, _task, _score_format: _format_first_line_or_dash(result.judge_reasoning)
    ),
    DetailsColumnKey.ERROR: (
        lambda result, _task, _score_format: _format_first_line_or_dash(result.error_message)
    ),
    DetailsColumnKey.ATTEMPTS: lambda result, _task, _score_format: str(len(result.attempts)),
    DetailsColumnKey.STARTED_AT: lambda result, _task, _score_format: result.started_at or _EM_DASH,
    DetailsColumnKey.FINISHED_AT: lambda result, _task, _score_format: (
        result.finished_at or _EM_DASH
    ),
}


def _format_cell(
    column: DetailsColumnKey,
    result: BenchmarkResult,
    task: BenchmarkTask | None,
    score_display_format: str,
) -> str:
    """Format one table cell via the per-column formatter dispatch table (details_tab.md#3).

    Args:
        column: The column to format.
        result: The row's result.
        task: The row's joined task, or None when it is no longer in the run's task set.
        score_display_format: "decimal" or "percentage" -- the Cosine Score display setting.

    Returns:
        The cell's display text; None values always render as an em-dash, never 0.
    """
    return _CELL_FORMATTERS[column](result, task, score_display_format)


def _passes_chip[T](allowed: tuple[T, ...], value: T) -> bool:
    """Return True for a result-derived chip filter: empty (all-selected) always passes."""
    return not allowed or value in allowed


def _passes_task_chip[T](
    allowed: tuple[T, ...], task: BenchmarkTask | None, getter: Callable[[BenchmarkTask], T]
) -> bool:
    """Return True for a task-derived chip filter.

    An empty filter (all-selected) always passes; an active filter fails when
    the task is unknown, since its value cannot be evaluated.
    """
    if not allowed:
        return True
    return task is not None and getter(task) in allowed


def _passes_filters(
    result: BenchmarkResult, task: BenchmarkTask | None, filters: DetailsFilters
) -> bool:
    """Return True when a result survives the seven filter-bar chips (details_tab.md#5)."""
    return (
        _passes_chip(filters.models, (result.provider_id, result.model_name))
        and _passes_chip(filters.tasks, result.task_id)
        and _passes_task_chip(filters.categories, task, lambda t: t.category)
        and _passes_chip(filters.statuses, result.status)
        and _passes_chip(filters.verdicts, result.verdict)
        and _passes_chip(filters.layers, result.resolution_layer)
        and _passes_task_chip(filters.difficulties, task, lambda t: t.difficulty)
    )


def _passes_column_filters(
    result: BenchmarkResult,
    task: BenchmarkTask | None,
    column_filters: tuple[ColumnFilterEntry, ...],
    score_display_format: str,
) -> bool:
    """Return True when a result survives every active per-column header filter."""
    for entry in column_filters:
        cell = _format_cell(entry.column, result, task, score_display_format)
        if cell not in entry.allowed_values:
            return False
    return True


def _sort_key(
    column: DetailsColumnKey, result: BenchmarkResult, task: BenchmarkTask | None
) -> tuple[int, float | str]:
    """Compute a row's sort key for the given column.

    Numeric columns sort numerically with an em-dash (None) value sorted lowest;
    every other column sorts lexicographically on its formatted display text.
    """
    numeric_fields: dict[DetailsColumnKey, float | None] = {
        DetailsColumnKey.TIME_MS: result.total_time_ms,
        DetailsColumnKey.TTFT_MS: result.ttft_ms,
        DetailsColumnKey.PROMPT_TOKENS: result.prompt_tokens,
        DetailsColumnKey.TOKENS: result.completion_tokens,
        DetailsColumnKey.TPS: result.tokens_per_second,
        DetailsColumnKey.COSINE_SCORE: result.cosine_similarity,
        DetailsColumnKey.ATTEMPTS: float(len(result.attempts)),
    }
    if column in numeric_fields:
        value = numeric_fields[column]
        return (0, float("-inf")) if value is None else (1, value)
    return (1, _format_cell(column, result, task, "decimal"))


def map_details_rows(
    *,
    results: tuple[BenchmarkResult, ...],
    tasks_by_id: dict[str, BenchmarkTask],
    run_mode: RunMode,  # noqa: ARG001  # accepted for call-site symmetry with Task 8's
    # DetailsTabController; view state is always looked up per-run_id with the same
    # run_mode it was written with, so no cross-mode filtering is needed here
    view_state: DetailsViewState,
    score_display_format: str,
) -> DetailsViewModel:
    """Filter, sort, and format the run's results into the Details table's view model.

    Row-removing only, per this tab's design constraint -- no re-aggregation
    (unlike the Summary tab).

    Args:
        results: The selected run's current result rows, in arbitrary order.
        tasks_by_id: The run's frozen tasks, keyed by task_id.
        run_mode: The selected run's mode; unused here, kept for call-site
            symmetry with Task 8's ``DetailsTabController``.
        view_state: The tab's current filters/columns/sort state.
        score_display_format: "decimal" or "percentage" -- the Cosine Score display setting.

    Returns:
        The Details tab's full render state.
    """
    filtered = [
        r
        for r in results
        if _passes_filters(r, tasks_by_id.get(r.task_id), view_state.filters)
        and _passes_column_filters(
            r, tasks_by_id.get(r.task_id), view_state.filters.column_filters, score_display_format
        )
    ]
    if view_state.sort.column is not None:
        sort_column = view_state.sort.column
        filtered.sort(
            key=lambda r: _sort_key(sort_column, r, tasks_by_id.get(r.task_id)),
            reverse=view_state.sort.descending,
        )
    visible_columns = tuple(c for c in view_state.columns.order if c in view_state.columns.visible)
    rows = tuple(
        DetailRowViewModel(
            result_id=r.result_id,
            cells=tuple(
                _format_cell(c, r, tasks_by_id.get(r.task_id), score_display_format)
                for c in visible_columns
            ),
        )
        for r in filtered
    )
    empty_message = None
    if not results:
        empty_message = "Detailed results will appear here once tasks complete."
    elif not rows:
        empty_message = "No rows match the current filters."
    return DetailsViewModel(
        columns=tuple(column_label(c) for c in visible_columns),
        rows=rows,
        selected_result_id=None,
        detail_panel=None,
        empty_state_message=empty_message,
    )


def _identity_fields(
    result: BenchmarkResult, task: BenchmarkTask | None, run_mode: RunMode
) -> tuple[tuple[str, str], ...]:
    """Build the identity & meta key/value grid (details_tab.md#9 section 1).

    Every value is labelled; a None/absent value renders as an em dash so the
    field stays visible.
    """
    task_fields: tuple[tuple[str, str], ...] = (
        ("Category", task.category if task is not None else _EM_DASH),
        ("Sub-category", task.sub_category if task is not None else _EM_DASH),
        ("Difficulty", task.difficulty.value if task is not None else _EM_DASH),
        ("Cosine enabled", str(task.cosine_enabled) if task is not None else _EM_DASH),
    )
    layer = result.resolution_layer.value if result.resolution_layer is not None else _EM_DASH
    return (
        ("Provider", result.provider_name),
        ("Model", result.model_name),
        ("Run mode", run_mode.value),
        ("Task ID", result.task_id),
        *task_fields,
        ("Total time (ms)", _format_optional_int(result.total_time_ms)),
        ("TTFT (ms)", _format_optional_int(result.ttft_ms)),
        ("Tokens per second", _format_tps(result)),
        ("Prompt tokens", _format_optional_int(result.prompt_tokens)),
        ("Completion tokens", _format_optional_int(result.completion_tokens)),
        ("Status", result.status.value),
        ("Verdict", _format_verdict(result.verdict)),
        ("Resolution layer", layer),
        ("Cosine Score", _format_cosine_score(result, "decimal")),
        ("Attempts", str(len(result.attempts))),
        ("Started at", result.started_at or _EM_DASH),
        ("Finished at", result.finished_at or _EM_DASH),
    )


def _judge_phase_row(result: BenchmarkResult) -> PhaseEvaluationRow:
    """Build the judge phase's per-phase-evaluation row, incl. the FAILED_JUDGE_TIMEOUT
    special-cased descriptions (details_tab.md#11)."""
    if result.status == ResultStatus.FAILED_JUDGE_TIMEOUT:
        exhausted = result.error_message is not None and "exhausted" in result.error_message.lower()
        description = (
            "Judge: did not complete — adaptive budget exhausted"
            if exhausted
            else "Judge: skipped — judge model excluded for the rest of the run"
        )
        return PhaseEvaluationRow(
            phase_name="Judge",
            outcome="did not complete",
            measurement=_EM_DASH,
            description=description,
        )
    if result.judge_verdict is None:
        return PhaseEvaluationRow(
            phase_name="Judge",
            outcome=_EM_DASH,
            measurement=_EM_DASH,
            description="Judge phase did not run.",
        )
    return PhaseEvaluationRow(
        phase_name="Judge",
        outcome=_format_verdict(result.judge_verdict),
        measurement=_EM_DASH,
        description="The judge model evaluated the response and returned a binary verdict.",
    )


def _phase_evaluations(result: BenchmarkResult) -> tuple[PhaseEvaluationRow, ...]:
    """Build one row per phase that ran: sanity check, keyword, cosine, judge (§9 section 5)."""
    rows: list[PhaseEvaluationRow] = []
    if result.sanity_check_passed is not None:
        outcome = "ok" if result.sanity_check_passed else "failed"
        rows.append(
            PhaseEvaluationRow(
                phase_name="Sanity check",
                outcome=outcome,
                measurement=_EM_DASH,
                description="Checked the response was non-empty and well-formed.",
            )
        )
    if result.keyword_verdict is not None:
        term_count = len(result.terms)
        rows.append(
            PhaseEvaluationRow(
                phase_name="Keyword",
                outcome=_format_verdict(result.keyword_verdict),
                measurement=f"{term_count} term(s) checked",
                description="Matched required/forbidden terms against the response.",
            )
        )
    if result.cosine_similarity is not None:
        rows.append(
            PhaseEvaluationRow(
                phase_name="Cosine",
                outcome=_format_verdict(result.cosine_verdict),
                measurement=_format_cosine_score(result, "decimal"),
                description="Compared the response to the golden answer by cosine similarity.",
            )
        )
    if result.judge_verdict is not None or result.status == ResultStatus.FAILED_JUDGE_TIMEOUT:
        rows.append(_judge_phase_row(result))
    return tuple(rows)


def _attempt_rows(result: BenchmarkResult) -> tuple[AttemptRow, ...]:
    """Map the result's raw attempt history to the panel's attempt-history section
    (details_tab.md#9 section 8)."""
    return tuple(
        AttemptRow(
            attempt_index=a.attempt_index,
            timeout_ms=a.timeout_ms,
            duration_ms=a.duration_ms,
            outcome=a.outcome.value,
            error_kind=a.error_kind.value if a.error_kind is not None else None,
            error_message=a.error_message,
        )
        for a in result.attempts
    )


def build_detail_panel(
    *, result: BenchmarkResult, task: BenchmarkTask | None, run_mode: RunMode
) -> ResultDetailViewModel:
    """Assemble the Task Detail Panel's full record for the selected result (details_tab.md#9).

    Args:
        result: The selected result row.
        task: The result's joined task, or None when it is no longer in the run's task set.
        run_mode: The selected run's mode, shown in the identity grid.

    Returns:
        The panel's full render state: identity/meta grid, prompts, golden answer, model
        response, per-phase evaluation, judge reasoning, error, and attempt history.
    """
    return ResultDetailViewModel(
        result_id=result.result_id,
        identity_fields=_identity_fields(result, task, run_mode),
        system_prompt=result.system_prompt_sent,
        user_prompt=result.user_prompt_sent,
        golden_answer=task.golden_answer if task is not None else None,
        model_response=result.sanitized_response,
        has_thinking_block=result.has_thinking_block,
        raw_response=result.raw_response,
        phase_evaluations=_phase_evaluations(result),
        judge_reasoning=result.judge_reasoning or "(none)",
        error_message=result.error_message or "(none)",
        attempts=_attempt_rows(result),
    )
