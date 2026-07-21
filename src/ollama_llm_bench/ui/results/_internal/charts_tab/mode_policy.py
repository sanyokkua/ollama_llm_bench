"""Pure mode-availability and skip-empty navigation logic for the Charts tab (STORY-064).

Source of truth: ``docs/v3_specification/05_Result_Widget/tabs/charts_tab.md`` §4
(mode-availability matrix), §7 (prev/next navigation and the skip-empty rule).
Imports no Qt symbol -- testable with no ``QApplication``.
"""

from collections.abc import Callable
from typing import Final

from ollama_llm_bench.backend.domain import ChartKind, RunMode

__all__: list[str] = [
    "SIX_CHART_OFFERED_KINDS",
    "TWELVE_CHART_OFFERED_KINDS",
    "first_offered_chart_kind",
    "next_navigable_index",
    "offered_chart_kinds",
    "prev_navigable_index",
]

# The six charts SYNTHETIC/TASKS offer, in mode-offered order (charts_tab.md#4): 1, 2, 3, 4, 8, 12.
SIX_CHART_OFFERED_KINDS: Final[tuple[ChartKind, ...]] = (
    ChartKind.AVG_TTFT_PER_MODEL,
    ChartKind.AVG_TPS_PER_MODEL,
    ChartKind.AVG_TIME_PER_MODEL,
    ChartKind.SUCCESS_FAILED_INCOMPLETE_STACKED,
    ChartKind.TIME_VS_TOKENS_SCATTER,
    ChartKind.TOKENS_PER_TASK_BOX,
)

# GRADED offers all twelve, in ChartKind's own declaration order (charts_tab.md#4).
TWELVE_CHART_OFFERED_KINDS: Final[tuple[ChartKind, ...]] = tuple(ChartKind)


def offered_chart_kinds(run_mode: RunMode) -> tuple[ChartKind, ...]:
    """Return the mode-offered chart kinds, in mode-offered order.

    Args:
        run_mode: The selected run's mode.

    Returns:
        The six-chart set for ``SYNTHETIC``/``TASKS``, or all twelve for
        ``GRADED`` (charts_tab.md#4).
    """
    if run_mode is RunMode.GRADED:
        return TWELVE_CHART_OFFERED_KINDS
    return SIX_CHART_OFFERED_KINDS


def first_offered_chart_kind(run_mode: RunMode) -> ChartKind:
    """Return the first mode-offered chart kind, seeding a fresh view state.

    Args:
        run_mode: The selected run's mode.

    Returns:
        The mode's first offered ``ChartKind`` (charts_tab.md#13).
    """
    return offered_chart_kinds(run_mode)[0]


def next_navigable_index(
    *,
    current_index: int,
    offered: tuple[ChartKind, ...],
    has_data: Callable[[ChartKind], bool],
) -> int | None:
    """Return the next populated chart's index, skipping offered-but-empty charts.

    Never wraps (charts_tab.md#7).

    Args:
        current_index: The active chart's index within ``offered``.
        offered: The mode-offered chart kinds, in mode-offered order.
        has_data: Returns whether a given chart kind currently has data.

    Returns:
        The next populated index, or ``None`` when no populated chart remains
        after ``current_index`` -- the next button is then disabled.
    """
    for index in range(current_index + 1, len(offered)):
        if has_data(offered[index]):
            return index
    return None


def prev_navigable_index(
    *,
    current_index: int,
    offered: tuple[ChartKind, ...],
    has_data: Callable[[ChartKind], bool],
) -> int | None:
    """Return the previous populated chart's index, skipping offered-but-empty charts.

    Never wraps (charts_tab.md#7).

    Args:
        current_index: The active chart's index within ``offered``.
        offered: The mode-offered chart kinds, in mode-offered order.
        has_data: Returns whether a given chart kind currently has data.

    Returns:
        The previous populated index, or ``None`` when no populated chart
        remains before ``current_index`` -- the prev button is then disabled.
    """
    for index in range(current_index - 1, -1, -1):
        if has_data(offered[index]):
            return index
    return None
