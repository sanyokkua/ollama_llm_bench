"""Pure row-mapping, filtering, and formatting logic for the Result widget's Details tab.

Imports no Qt symbol — testable with no QApplication.
"""

from enum import StrEnum
from typing import Final

import msgspec

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
