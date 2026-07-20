"""Pure ``(results, tasks, view_state) -> SummaryViewModel`` aggregation for the Summary
tab (STORY-062). Holds no Qt import and no store -- a pure function of its inputs.

Source of truth: ``docs/v3_specification/05_Result_Widget/tabs/summary_tab.md`` §§3-9,
11 (identity model, column reference, mode visibility, filter bar, sorting, empty states,
export mirroring); ``08_Cross_Cutting/08-G_feature_flags.md`` (``eval.min_sample_size``
default ``5``, ``eval.min_cosine_coverage`` default ``0.8``, ``ui.score_display_format``
enum ``decimal``/``percent``/``letter``, default ``decimal``).

Two glyphs used below are resolved against the spec as follows:

- The **partial cosine-coverage** marker is spec-mandated verbatim: ``⚠`` (§4.1, DD-63).
- The **low-sample** marker (SPEC-092) has no textual glyph fixed anywhere in the vendored
  spec for a *table cell* -- only a chart-level hatch-fill + ``n=N`` annotation is specified
  (``11_Services_and_Algorithms/13_CHART_AGGREGATORS.md``). This module uses the documented
  fallback ``†`` appended to the cell text, so a tiny sample is still visibly flagged in the
  Summary table without inventing an un-spec'd visual treatment.

``ui.score_display_format``'s ``letter`` option has no letter-grade boundary table anywhere
in the vendored spec; this module renders ``letter`` identically to ``decimal`` rather than
inventing grade thresholds (a documented, reported simplification -- see the story's return
summary).
"""

from collections import Counter
from collections.abc import Mapping
from enum import StrEnum
from statistics import median

import msgspec

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkTask,
    Difficulty,
    ResolutionLayer,
    ResultStatus,
    RunMode,
    TaskId,
    Verdict,
)
from ollama_llm_bench.ui.results.models import SummaryViewModel

__all__: list[str] = [
    "ChipDomains",
    "ColumnFilterEntry",
    "SummaryColumnKey",
    "SummaryColumnLayout",
    "SummaryFilters",
    "SummarySort",
    "SummaryViewState",
    "aggregate_summary",
    "chip_domains",
    "column_filter_domain",
    "column_label",
    "decode_view_state",
    "default_view_state",
    "encode_view_state",
    "offered_columns",
]

_EM_DASH = "—"
_LOW_SAMPLE_MARKER = "†"
_PARTIAL_COVERAGE_MARKER = "⚠"
_MIN_SAMPLE_SIZE_DEFAULT = 5
_MIN_COSINE_COVERAGE_DEFAULT = 0.8
_COMPOSITE_KEY_SEP = "\x1f"

_MSG_NO_RESULTS = "This run has no results yet."
_MSG_NO_COMPLETED = "No completed results yet — aggregates will fill in as tasks finish."
_MSG_FILTERED_EMPTY = "No rows match the current filters."

_COMPLETED_STATUSES = frozenset({ResultStatus.COMPLETED})
_FAILED_STATUSES = frozenset(
    {
        ResultStatus.FAILED_INFERENCE,
        ResultStatus.FAILED_PROVIDER,
        ResultStatus.FAILED_TIMEOUT,
        ResultStatus.FAILED_JUDGE_TIMEOUT,
        ResultStatus.ERRORED,
    }
)
_INCOMPLETE_STATUSES = frozenset(
    {
        ResultStatus.PENDING,
        ResultStatus.RUNNING_INFERENCE,
        ResultStatus.AWAITING_KEYWORD_CHECK,
        ResultStatus.AWAITING_COSINE_CHECK,
        ResultStatus.AWAITING_JUDGE_CHECK,
    }
)


class SummaryColumnKey(StrEnum):
    """Every column the Summary table can offer (§4-column-reference, master order)."""

    PROVIDER_MODEL = "provider_model"
    TASKS = "tasks"
    COMPLETED = "completed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"
    AVG_TIME_S = "avg_time_s"
    MEDIAN_TIME_S = "median_time_s"
    AVG_TTFT_S = "avg_ttft_s"
    AVG_TPS = "avg_tps"
    AVG_TOKENS = "avg_tokens"
    PASS_RATE = "pass_rate"  # noqa: S105  # enum member, not a credential
    COSINE_SCORE = "cosine_score"
    JUDGE_PASS = "judge_pass"  # noqa: S105  # enum member, not a credential
    JUDGE_FAIL = "judge_fail"
    TIMEOUT_FAILURES = "timeout_failures"
    JUDGE_TIMEOUT_FAILURES = "judge_timeout_failures"
    PROVIDER_FAILURES = "provider_failures"
    LAYER_MIX = "layer_mix"
    AVG_ATTEMPTS = "avg_attempts"


_COLUMN_ORDER: tuple[SummaryColumnKey, ...] = (
    SummaryColumnKey.PROVIDER_MODEL,
    SummaryColumnKey.TASKS,
    SummaryColumnKey.COMPLETED,
    SummaryColumnKey.FAILED,
    SummaryColumnKey.INCOMPLETE,
    SummaryColumnKey.AVG_TIME_S,
    SummaryColumnKey.MEDIAN_TIME_S,
    SummaryColumnKey.AVG_TTFT_S,
    SummaryColumnKey.AVG_TPS,
    SummaryColumnKey.AVG_TOKENS,
    SummaryColumnKey.PASS_RATE,
    SummaryColumnKey.COSINE_SCORE,
    SummaryColumnKey.JUDGE_PASS,
    SummaryColumnKey.JUDGE_FAIL,
    SummaryColumnKey.TIMEOUT_FAILURES,
    SummaryColumnKey.JUDGE_TIMEOUT_FAILURES,
    SummaryColumnKey.PROVIDER_FAILURES,
    SummaryColumnKey.LAYER_MIX,
    SummaryColumnKey.AVG_ATTEMPTS,
)

_COLUMN_LABELS: dict[SummaryColumnKey, str] = {
    SummaryColumnKey.PROVIDER_MODEL: "Provider / Model",
    SummaryColumnKey.TASKS: "Tasks",
    SummaryColumnKey.COMPLETED: "Completed",
    SummaryColumnKey.FAILED: "Failed",
    SummaryColumnKey.INCOMPLETE: "Incomplete",
    SummaryColumnKey.AVG_TIME_S: "Avg Time (s)",
    SummaryColumnKey.MEDIAN_TIME_S: "Median Time (s)",
    SummaryColumnKey.AVG_TTFT_S: "Avg TTFT (s)",
    SummaryColumnKey.AVG_TPS: "Avg TPS",
    SummaryColumnKey.AVG_TOKENS: "Avg Tokens",
    SummaryColumnKey.PASS_RATE: "Pass Rate",
    SummaryColumnKey.COSINE_SCORE: "Cosine Score",
    SummaryColumnKey.JUDGE_PASS: "Judge PASS",
    SummaryColumnKey.JUDGE_FAIL: "Judge FAIL",
    SummaryColumnKey.TIMEOUT_FAILURES: "Timeout failures",
    SummaryColumnKey.JUDGE_TIMEOUT_FAILURES: "Judge-timeout failures",
    SummaryColumnKey.PROVIDER_FAILURES: "Provider failures",
    SummaryColumnKey.LAYER_MIX: "Layer mix",
    SummaryColumnKey.AVG_ATTEMPTS: "Avg attempts",
}

_GRADED_ONLY_COLUMNS = frozenset(
    {
        SummaryColumnKey.PASS_RATE,
        SummaryColumnKey.COSINE_SCORE,
        SummaryColumnKey.JUDGE_PASS,
        SummaryColumnKey.JUDGE_FAIL,
        SummaryColumnKey.JUDGE_TIMEOUT_FAILURES,
        SummaryColumnKey.LAYER_MIX,
    }
)

_DEFAULT_VISIBLE_COLUMNS = frozenset(
    {
        SummaryColumnKey.PROVIDER_MODEL,
        SummaryColumnKey.TASKS,
        SummaryColumnKey.FAILED,
        SummaryColumnKey.AVG_TIME_S,
        SummaryColumnKey.AVG_TTFT_S,
        SummaryColumnKey.AVG_TPS,
        SummaryColumnKey.AVG_TOKENS,
        SummaryColumnKey.PASS_RATE,
        SummaryColumnKey.COSINE_SCORE,
    }
)

# Columns SPEC-092 flags with the low-sample marker when the group's completed count is
# below ``eval.min_sample_size`` ("the Pass Rate ... and the throughput aggregates").
_LOW_SAMPLE_ELIGIBLE_COLUMNS = frozenset(
    {
        SummaryColumnKey.PASS_RATE,
        SummaryColumnKey.AVG_TIME_S,
        SummaryColumnKey.MEDIAN_TIME_S,
        SummaryColumnKey.AVG_TTFT_S,
        SummaryColumnKey.AVG_TPS,
        SummaryColumnKey.AVG_TOKENS,
    }
)

# The per-column filter's fixed domain for the three §6.1-filterable columns (a
# documented scope simplification -- see the module docstring).
_COLUMN_FILTER_DOMAINS: dict[SummaryColumnKey, tuple[str, ...]] = {
    SummaryColumnKey.FAILED: tuple(status.value for status in _FAILED_STATUSES),
    SummaryColumnKey.INCOMPLETE: tuple(status.value for status in _INCOMPLETE_STATUSES),
    SummaryColumnKey.LAYER_MIX: tuple(layer.value for layer in ResolutionLayer),
}

type _Cell = tuple[str, float | str]
type _GroupKey = tuple[str, str]


class SummaryFilters(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The four filter-bar chips' current selection (§6). ``None`` means "all"."""

    models: frozenset[str] | None = None
    verdicts: frozenset[str] = frozenset({"pass", "fail", "ungraded"})
    difficulties: frozenset[str] = frozenset(
        {Difficulty.EASY.value, Difficulty.MEDIUM.value, Difficulty.HARD.value}
    )
    categories: frozenset[str] | None = None


class ColumnFilterEntry(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One active per-column filter (§6.1)."""

    column: SummaryColumnKey
    selected_values: frozenset[str]


class SummaryColumnLayout(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The current column-visibility set and column order (§7)."""

    visible: frozenset[SummaryColumnKey]
    order: tuple[SummaryColumnKey, ...]


class SummarySort(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The active sort column and direction (§8)."""

    column: SummaryColumnKey | None = None
    descending: bool = True


class SummaryViewState(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Summary tab's whole per-run persisted view state (§12)."""

    filters: SummaryFilters = SummaryFilters()
    column_filters: tuple[ColumnFilterEntry, ...] = ()
    layout: SummaryColumnLayout
    sort: SummarySort = SummarySort(column=SummaryColumnKey.AVG_TPS, descending=True)


class ChipDomains(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The distinct chip option domains, computed from the full unfiltered run (§6)."""

    models: tuple[tuple[str, str], ...]  # (composite_key, "<provider_name> / <model_name>")
    verdicts: tuple[str, ...]
    difficulties: tuple[str, ...]
    categories: tuple[str, ...]


def offered_columns(run_mode: RunMode) -> tuple[SummaryColumnKey, ...]:
    """Return the mode-offered columns, in the master §4 order.

    Args:
        run_mode: The displayed run's mode.

    Returns:
        All 19 columns for ``GRADED``; the 13 non-grading columns otherwise (§5).
    """
    if run_mode is RunMode.GRADED:
        return _COLUMN_ORDER
    return tuple(column for column in _COLUMN_ORDER if column not in _GRADED_ONLY_COLUMNS)


def column_label(column: SummaryColumnKey) -> str:
    """Return a column's plain display label (no sort caret).

    Used by the column-visibility popover and the per-column filter menu, which
    need the label without ``select.py``'s private ``_COLUMN_LABELS`` mapping.
    """
    return _COLUMN_LABELS[column]


def column_filter_domain(column: SummaryColumnKey) -> tuple[str, ...] | None:
    """Return the fixed per-column filter domain for a right-click-filterable column.

    Per the story's documented scope simplification, the domain is the column's
    fixed, closed status/layer set -- not a dynamic scan of values actually present
    in the run's contributing rows.

    Args:
        column: The column the user right-clicked.

    Returns:
        The domain's string values for ``FAILED``/``INCOMPLETE``/``LAYER_MIX``;
        ``None`` for every other column (no per-column filter is offered).
    """
    return _COLUMN_FILTER_DOMAINS.get(column)


def default_view_state(run_mode: RunMode) -> SummaryViewState:
    """Build the built-in default view state for a run opened for the first time (§12).

    Args:
        run_mode: The run's mode; decides the offered/default-visible column set.

    Returns:
        All filters selected, no per-column filters, the mode's default column
        visibility and order, and the default Avg-TPS-descending sort.
    """
    offered = offered_columns(run_mode)
    visible = frozenset(column for column in offered if column in _DEFAULT_VISIBLE_COLUMNS)
    return SummaryViewState(layout=SummaryColumnLayout(visible=visible, order=offered))


def encode_view_state(state: SummaryViewState) -> str:
    """Serialise a view state to the string persisted through ``PerRunViewStateStore``."""
    return msgspec.json.encode(state).decode("utf-8")


def decode_view_state(raw: str) -> SummaryViewState:
    """Parse a previously-persisted view-state string back into a ``SummaryViewState``."""
    return msgspec.json.decode(raw.encode("utf-8"), type=SummaryViewState)


def chip_domains(
    *, results: tuple[BenchmarkResult, ...], tasks_by_id: Mapping[TaskId, BenchmarkTask]
) -> ChipDomains:
    """Compute the four chips' option domains from the run's full, unfiltered results.

    Args:
        results: Every result of the displayed run (never the post-filter subset).
        tasks_by_id: Every task the run's results reference, keyed by ``task_id``.

    Returns:
        The distinct Models/Verdict/Difficulty/Category domains.
    """
    models: dict[str, str] = {}
    categories: dict[str, None] = {}
    for result in results:
        models.setdefault(
            _composite_key(result.provider_id, result.model_name), _group_label(result)
        )
        categories.setdefault(tasks_by_id[result.task_id].category, None)
    return ChipDomains(
        models=tuple(models.items()),
        verdicts=("pass", "fail", "ungraded"),
        difficulties=tuple(member.value for member in Difficulty),
        categories=tuple(categories.keys()),
    )


def aggregate_summary(
    *,
    results: tuple[BenchmarkResult, ...],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    run_mode: RunMode,
    view_state: SummaryViewState,
    score_display_format: str | None,
) -> SummaryViewModel:
    """Derive the Summary tab's render state from a run's results and its view state.

    Args:
        results: Every result of the displayed run.
        tasks_by_id: Every task the run's results reference, keyed by ``task_id``.
        run_mode: The run's mode; decides the offered column set (§5).
        view_state: The current filters, column layout, and sort (§6-§8, §12).
        score_display_format: ``ui.score_display_format`` (``decimal``/``percent``/
            ``letter``), or ``None`` for the ``decimal`` default.

    Returns:
        The mode-offered, visible, sorted columns; one row per surviving model group;
        and the empty-state message for the current state (§9), or ``None``.
    """
    offered = offered_columns(run_mode)
    visible_in_order = tuple(
        column
        for column in view_state.layout.order
        if column in view_state.layout.visible and column in offered
    )
    columns = tuple(_column_header(column, view_state.sort) for column in visible_in_order)

    if not results:
        return SummaryViewModel(columns=columns, rows=(), empty_state_message=_MSG_NO_RESULTS)

    filtered = _apply_row_filters(
        results=results,
        tasks_by_id=tasks_by_id,
        filters=view_state.filters,
        column_filters=view_state.column_filters,
    )
    groups = _apply_models_filter(_group_by_model(filtered), view_state.filters.models)
    rows = _build_rows(
        groups=groups,
        tasks_by_id=tasks_by_id,
        visible_in_order=visible_in_order,
        sort=view_state.sort,
        score_display_format=score_display_format,
    )
    has_completed = any(result.status is ResultStatus.COMPLETED for result in results)
    message = _resolve_empty_message(has_completed=has_completed, has_groups=bool(groups))
    return SummaryViewModel(columns=columns, rows=rows, empty_state_message=message)


def _resolve_empty_message(*, has_completed: bool, has_groups: bool) -> str | None:
    if not has_completed:
        return _MSG_NO_COMPLETED
    if not has_groups:
        return _MSG_FILTERED_EMPTY
    return None


def _column_header(column: SummaryColumnKey, sort: SummarySort) -> str:
    label = _COLUMN_LABELS[column]
    if sort.column != column:
        return label
    return f"{label}{' ▼' if sort.descending else ' ▲'}"


def _composite_key(provider_id: str, model_name: str) -> str:
    return f"{provider_id}{_COMPOSITE_KEY_SEP}{model_name}"


def _group_label(result: BenchmarkResult) -> str:
    return f"{result.provider_name} / {result.model_name}"


def _apply_row_filters(
    *,
    results: tuple[BenchmarkResult, ...],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    filters: SummaryFilters,
    column_filters: tuple[ColumnFilterEntry, ...],
) -> tuple[BenchmarkResult, ...]:
    column_filter_map = {entry.column: entry.selected_values for entry in column_filters}
    kept: list[BenchmarkResult] = []
    for result in results:
        task = tasks_by_id[result.task_id]
        verdict_key = result.verdict.value if result.verdict is not None else "ungraded"
        if verdict_key not in filters.verdicts:
            continue
        if task.difficulty.value not in filters.difficulties:
            continue
        if filters.categories is not None and task.category not in filters.categories:
            continue
        if not _passes_column_filters(result, column_filter_map):
            continue
        kept.append(result)
    return tuple(kept)


def _passes_column_filters(
    result: BenchmarkResult, column_filter_map: Mapping[SummaryColumnKey, frozenset[str]]
) -> bool:
    checks: tuple[tuple[SummaryColumnKey, frozenset[str], str | None], ...] = (
        (
            SummaryColumnKey.FAILED,
            frozenset(status.value for status in _FAILED_STATUSES),
            result.status.value,
        ),
        (
            SummaryColumnKey.INCOMPLETE,
            frozenset(status.value for status in _INCOMPLETE_STATUSES),
            result.status.value,
        ),
        (
            SummaryColumnKey.LAYER_MIX,
            frozenset(layer.value for layer in ResolutionLayer),
            result.resolution_layer.value if result.resolution_layer is not None else None,
        ),
    )
    for column, domain_values, row_value in checks:
        selected = column_filter_map.get(column)
        if selected is None or row_value is None or row_value not in domain_values:
            continue
        if row_value not in selected:
            return False
    return True


def _group_by_model(results: tuple[BenchmarkResult, ...]) -> dict[_GroupKey, list[BenchmarkResult]]:
    groups: dict[_GroupKey, list[BenchmarkResult]] = {}
    for result in results:
        groups.setdefault((result.provider_id, result.model_name), []).append(result)
    return groups


def _apply_models_filter(
    groups: dict[_GroupKey, list[BenchmarkResult]], selected_models: frozenset[str] | None
) -> dict[_GroupKey, list[BenchmarkResult]]:
    if selected_models is None:
        return groups
    return {
        key: rows
        for key, rows in groups.items()
        if _composite_key(key[0], key[1]) in selected_models
    }


def _build_rows(
    *,
    groups: dict[_GroupKey, list[BenchmarkResult]],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    visible_in_order: tuple[SummaryColumnKey, ...],
    sort: SummarySort,
    score_display_format: str | None,
) -> tuple[tuple[str, ...], ...]:
    coverage_by_key = {
        key: _cosine_coverage(_completed_of(rows), tasks_by_id) for key, rows in groups.items()
    }
    any_group_meets_coverage = any(
        coverage is not None and coverage >= _MIN_COSINE_COVERAGE_DEFAULT
        for coverage in coverage_by_key.values()
    )
    aggregated: list[tuple[_GroupKey, dict[SummaryColumnKey, _Cell]]] = []
    for key, group_results in groups.items():
        coverage = coverage_by_key[key]
        flag_partial_coverage = (
            any_group_meets_coverage
            and coverage is not None
            and coverage < _MIN_COSINE_COVERAGE_DEFAULT
        )
        cells = _aggregate_group(
            group_results=group_results,
            score_display_format=score_display_format,
            flag_partial_coverage=flag_partial_coverage,
        )
        aggregated.append((key, cells))
    ordered = _sort_groups(aggregated, sort)
    return tuple(
        tuple(str(cells[column][0]) for column in visible_in_order) for _, cells in ordered
    )


def _completed_of(group_results: list[BenchmarkResult]) -> list[BenchmarkResult]:
    return [result for result in group_results if result.status in _COMPLETED_STATUSES]


def _sort_groups(
    aggregated: list[tuple[_GroupKey, dict[SummaryColumnKey, _Cell]]], sort: SummarySort
) -> list[tuple[_GroupKey, dict[SummaryColumnKey, _Cell]]]:
    if sort.column is None:
        return aggregated

    def _sort_value(item: tuple[_GroupKey, dict[SummaryColumnKey, _Cell]]) -> float | str:
        _, cells = item
        return cells[sort.column][1] if sort.column is not None else 0.0

    return sorted(aggregated, key=_sort_value, reverse=sort.descending)


def _aggregate_group(
    *,
    group_results: list[BenchmarkResult],
    score_display_format: str | None,
    flag_partial_coverage: bool,
) -> dict[SummaryColumnKey, _Cell]:
    completed = _completed_of(group_results)
    low_sample = len(completed) < _MIN_SAMPLE_SIZE_DEFAULT
    cells: dict[SummaryColumnKey, _Cell] = {
        SummaryColumnKey.PROVIDER_MODEL: (
            _group_label(group_results[0]),
            _group_label(group_results[0]),
        ),
        SummaryColumnKey.TASKS: _cell_count(len(group_results)),
        SummaryColumnKey.COMPLETED: _cell_count(len(completed)),
        SummaryColumnKey.FAILED: _cell_count(_count_status(group_results, _FAILED_STATUSES)),
        SummaryColumnKey.INCOMPLETE: _cell_count(
            _count_status(group_results, _INCOMPLETE_STATUSES)
        ),
        SummaryColumnKey.AVG_TIME_S: _mean_seconds([result.total_time_ms for result in completed]),
        SummaryColumnKey.MEDIAN_TIME_S: _median_seconds(
            [result.total_time_ms for result in completed]
        ),
        SummaryColumnKey.AVG_TTFT_S: _mean_seconds([result.ttft_ms for result in completed]),
        SummaryColumnKey.AVG_TPS: _aggregate_avg_tps(completed),
        SummaryColumnKey.AVG_TOKENS: _mean_tokens(
            [result.completion_tokens for result in completed]
        ),
        SummaryColumnKey.PASS_RATE: _pass_rate(completed, score_display_format),
        SummaryColumnKey.COSINE_SCORE: _cosine_cell(
            completed, score_display_format, flag_partial=flag_partial_coverage
        ),
        SummaryColumnKey.JUDGE_PASS: _cell_count(
            sum(1 for result in completed if result.judge_verdict is Verdict.PASS)
        ),
        SummaryColumnKey.JUDGE_FAIL: _cell_count(
            sum(1 for result in completed if result.judge_verdict is Verdict.FAIL)
        ),
        SummaryColumnKey.TIMEOUT_FAILURES: _cell_count(
            sum(1 for result in group_results if result.status is ResultStatus.FAILED_TIMEOUT)
        ),
        SummaryColumnKey.JUDGE_TIMEOUT_FAILURES: _cell_count(
            sum(1 for result in group_results if result.status is ResultStatus.FAILED_JUDGE_TIMEOUT)
        ),
        SummaryColumnKey.PROVIDER_FAILURES: _cell_count(
            sum(1 for result in group_results if result.status is ResultStatus.FAILED_PROVIDER)
        ),
        SummaryColumnKey.LAYER_MIX: _layer_mix_cell(completed),
        SummaryColumnKey.AVG_ATTEMPTS: _mean_attempts(group_results),
    }
    return _apply_low_sample_markers(cells, low_sample=low_sample)


def _apply_low_sample_markers(
    cells: dict[SummaryColumnKey, _Cell], *, low_sample: bool
) -> dict[SummaryColumnKey, _Cell]:
    if not low_sample:
        return cells
    for column in _LOW_SAMPLE_ELIGIBLE_COLUMNS:
        text, value = cells[column]
        if text != _EM_DASH:
            cells[column] = (f"{text} {_LOW_SAMPLE_MARKER}", value)
    return cells


def _count_status(results: list[BenchmarkResult], statuses: frozenset[ResultStatus]) -> int:
    return sum(1 for result in results if result.status in statuses)


def _cell_count(count: int) -> _Cell:
    return str(count), float(count)


def _mean_seconds(values_ms: list[int | None]) -> _Cell:
    seconds = [value / 1000 for value in values_ms if value is not None]
    if not seconds:
        return _EM_DASH, float("-inf")
    mean_value = sum(seconds) / len(seconds)
    return f"{mean_value:.2f}", mean_value


def _median_seconds(values_ms: list[int | None]) -> _Cell:
    seconds = [value / 1000 for value in values_ms if value is not None]
    if not seconds:
        return _EM_DASH, float("-inf")
    median_value = median(seconds)
    return f"{median_value:.2f}", median_value


def _mean_tokens(values: list[int | None]) -> _Cell:
    tokens = [value for value in values if value is not None]
    if not tokens:
        return _EM_DASH, float("-inf")
    mean_value = sum(tokens) / len(tokens)
    return str(round(mean_value)), mean_value


def _aggregate_avg_tps(completed: list[BenchmarkResult]) -> _Cell:
    contributing = [result for result in completed if result.tokens_per_second is not None]
    if not contributing:
        return _EM_DASH, float("-inf")
    values = [
        result.tokens_per_second for result in contributing if result.tokens_per_second is not None
    ]
    mean_value = sum(values) / len(values)
    prefix = ""
    if any(result.tokens_estimated for result in contributing):
        prefix += "≈"
    if any(result.has_thinking_block for result in contributing):
        prefix += "⧉"
    return f"{prefix}{mean_value:.1f}", mean_value


def _pass_rate(completed: list[BenchmarkResult], score_display_format: str | None) -> _Cell:
    if not completed:
        return _EM_DASH, float("-inf")
    passed = sum(1 for result in completed if result.verdict is Verdict.PASS)
    rate = passed / len(completed)
    return _format_score(rate, score_display_format=score_display_format), rate


def _cosine_cell(
    completed: list[BenchmarkResult], score_display_format: str | None, *, flag_partial: bool
) -> _Cell:
    values = [
        result.cosine_similarity for result in completed if result.cosine_similarity is not None
    ]
    if not values:
        return _EM_DASH, float("-inf")
    mean_value = sum(values) / len(values)
    text = _format_score(mean_value, score_display_format=score_display_format)
    if flag_partial:
        text = f"{text} {_PARTIAL_COVERAGE_MARKER}"
    return text, mean_value


def _format_score(value: float, *, score_display_format: str | None) -> str:
    fmt = score_display_format or "decimal"
    if fmt == "percent":
        return f"{value:.0%}"
    # "decimal" and the un-spec'd "letter" both render as a plain 0.00-1.00 decimal --
    # see the module docstring for why "letter" has no defined grade-boundary mapping.
    return f"{value:.2f}"


def _cosine_coverage(
    completed: list[BenchmarkResult], tasks_by_id: Mapping[TaskId, BenchmarkTask]
) -> float | None:
    eligible = [result for result in completed if _is_cosine_eligible(result, tasks_by_id)]
    if not eligible:
        return None
    covered = sum(1 for result in eligible if result.cosine_similarity is not None)
    return covered / len(eligible)


def _is_cosine_eligible(
    result: BenchmarkResult, tasks_by_id: Mapping[TaskId, BenchmarkTask]
) -> bool:
    task = tasks_by_id[result.task_id]
    return task.golden_answer is not None and task.cosine_enabled


def _layer_mix_cell(completed: list[BenchmarkResult]) -> _Cell:
    counts = Counter(
        result.resolution_layer for result in completed if result.resolution_layer is not None
    )
    if not counts:
        return _EM_DASH, float("-inf")
    text = (
        f"K{counts.get(ResolutionLayer.KEYWORD, 0)} "
        f"C{counts.get(ResolutionLayer.COSINE, 0)} "
        f"J{counts.get(ResolutionLayer.JUDGE, 0)} "
        f"S{counts.get(ResolutionLayer.SKIP, 0)}"
    )
    return text, float(sum(counts.values()))


def _mean_attempts(group_results: list[BenchmarkResult]) -> _Cell:
    if not group_results:
        return _EM_DASH, float("-inf")
    lengths = [len(result.attempts) for result in group_results]
    mean_value = sum(lengths) / len(lengths)
    return f"{mean_value:.1f}", mean_value
