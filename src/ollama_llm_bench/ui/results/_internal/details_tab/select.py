"""Pure row-mapping, filtering, and formatting logic for the Result widget's Details tab.

Imports no Qt symbol — testable with no QApplication.
"""

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


def encode_view_state(state: DetailsViewState) -> str:
    """Serialize a view state to the string persisted via ResultGateway.set_setting."""
    return msgspec.json.encode(state).decode("utf-8")


def decode_view_state(raw: str) -> DetailsViewState:
    """Deserialize a view state previously produced by encode_view_state."""
    return msgspec.json.decode(raw.encode("utf-8"), type=DetailsViewState)
