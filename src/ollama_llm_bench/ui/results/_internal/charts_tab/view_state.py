"""Private per-run, per-chart-kind persisted view state for the Charts tab (STORY-064).

Source of truth: ``docs/v3_specification/05_Result_Widget/tabs/charts_tab.md`` §13
(persistence). Mirrors ``details_tab/select.py``'s ``encode_view_state``/
``decode_view_state``/``default_view_state`` naming and ``msgspec.json``
serialization -- what ``PerRunViewStateStore.get_slice``/``set_slice`` take as
``encoder``/``decoder``/``default_factory``.
"""

import msgspec
import msgspec.json

from ollama_llm_bench.backend.domain import ChartKind, RunMode
from ollama_llm_bench.ui.results._internal.charts_tab import mode_policy

__all__: list[str] = [
    "ChartFilterState",
    "ChartsViewState",
    "decode_view_state",
    "default_view_state",
    "encode_view_state",
]


class ChartFilterState(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One chart kind's global filter selection plus its per-chart options
    (charts_tab.md#5, #6). An empty tuple means "all selected"."""

    models: tuple[tuple[str, str], ...] = ()
    statuses: tuple[str, ...] = ()
    verdicts: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    difficulties: tuple[str, ...] = ()
    options: dict[str, str] = msgspec.field(default_factory=dict)


class ChartsViewState(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Charts tab's full persisted per-run view state (charts_tab.md#13).

    ``filters_by_kind``/``hidden_series_by_kind`` are keyed by ``ChartKind.value``
    (a plain ``str`` key, since ``msgspec.json`` cannot use an enum as a dict key).
    """

    last_chart_kind: ChartKind
    outlier_exclusion: bool
    filters_by_kind: dict[str, ChartFilterState] = msgspec.field(default_factory=dict)
    hidden_series_by_kind: dict[str, tuple[str, ...]] = msgspec.field(default_factory=dict)


def default_view_state(run_mode: RunMode) -> ChartsViewState:
    """Build the built-in default Charts view state for a run's mode (charts_tab.md#13).

    Args:
        run_mode: The run's mode.

    Returns:
        All filters selected, the default per-chart options, no hidden series,
        the mode's first offered chart as the last-opened kind, and the outlier
        toggle defaulted on (the ``ui.charts_outlier_default`` built-in default).
    """
    return ChartsViewState(
        last_chart_kind=mode_policy.first_offered_chart_kind(run_mode),
        outlier_exclusion=True,
    )


def filter_state_for(state: ChartsViewState, chart_kind: ChartKind) -> ChartFilterState:
    """Return one chart kind's filter/option slice, or its default if unset.

    Args:
        state: The Charts tab's current view state.
        chart_kind: The chart kind whose filter slice to read.

    Returns:
        The stored ``ChartFilterState`` for ``chart_kind``, or an all-selected
        default when the chart kind has never been customised.
    """
    return state.filters_by_kind.get(chart_kind.value, ChartFilterState())


def hidden_series_for(state: ChartsViewState, chart_kind: ChartKind) -> tuple[str, ...]:
    """Return one chart kind's hidden legend series (charts_tab.md#6, kinds 4/7).

    Args:
        state: The Charts tab's current view state.
        chart_kind: The chart kind whose hidden-series set to read.

    Returns:
        The stored hidden-series tuple, or an empty tuple when none is hidden.
    """
    return state.hidden_series_by_kind.get(chart_kind.value, ())


def encode_view_state(state: ChartsViewState) -> str:
    """Serialize a view state to the string persisted via ``ResultGateway.set_setting``."""
    return msgspec.json.encode(state).decode("utf-8")


def decode_view_state(raw: str) -> ChartsViewState:
    """Deserialize a view state previously produced by ``encode_view_state``."""
    return msgspec.json.decode(raw.encode("utf-8"), type=ChartsViewState)
