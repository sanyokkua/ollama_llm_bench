"""``ChartsTabController`` -- the Charts tab's sub-controller (STORY-064).

Source of truth: ``docs/v3_specification/05_Result_Widget/implementation_structure.md``
§5.3 (concern, subscription, derivation, view-state slice); ``tabs/charts_tab.md``
§4 (mode-availability), §7 (navigation), §8 (drill-down), §9 (detach), §12 (export).
Depends only on ``ResultGateway``, the ``EventBus``, and the shared
``PerRunViewStateStore`` (D-R-06) -- never a raw backend Store/Service Protocol.

The ``ResultGateway.chart_data(run_id, chart_kind)`` contract (08-E §7b.5, frozen by
STORY-061) takes no ``ChartFilters`` parameter, so this controller cannot forward the
tab's filter-chip/per-chart-option selection into the aggregator -- see this story's
Notes section for the documented gap. Every offered chart's full-run data is fetched
on each recompute; the tab performs no aggregation arithmetic of its own.
"""

from collections.abc import Callable
from typing import Protocol

import msgspec
import structlog

from ollama_llm_bench.backend.domain import ChartData, ChartKind, HeatmapData, RunId, RunMode
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.ui.results._internal.charts_tab import mode_policy, painting
from ollama_llm_bench.ui.results._internal.charts_tab.select import (
    ChartsSelectionInput,
    select_charts_view_model,
)
from ollama_llm_bench.ui.results._internal.charts_tab.view_state import (
    ChartFilterState,
    ChartsViewState,
    decode_view_state,
    default_view_state,
    encode_view_state,
    filter_state_for,
)
from ollama_llm_bench.ui.results._internal.theme_lookup import resolve_theme_tokens
from ollama_llm_bench.ui.results._internal.view_state_store import PerRunViewStateStore
from ollama_llm_bench.ui.results.models import ChartDrilldownRequest, ChartsViewModel
from ollama_llm_bench.ui.results.protocols import ResultGateway
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager, make_dark_theme_tokens

__all__: list[str] = ["ChartsTabController", "ChartsTabViewProtocol"]

logger = structlog.get_logger(__name__)

_SLICE_KEY = "charts.view_state"


class ChartsTabViewProtocol(Protocol):
    """The subset of ``ChartsTabView``'s surface this controller drives.

    Declared locally, structurally, matching ``DetailsTabViewProtocol``'s
    precedent (STORY-063) -- keeps ``bind()`` fully typed with zero
    ``# type: ignore`` regardless of construction order between the two modules.
    """

    def apply(self, view_model: ChartsViewModel) -> None:
        """Render the derived ``ChartsViewModel``."""
        ...

    def apply_no_run(self, message: str) -> None:
        """Render the tab's empty state before any run is selected."""
        ...

    def set_export_enabled(self, *, enabled: bool) -> None:
        """Enable/disable this tab's export action for the run's terminal state."""
        ...


class ChartsTabController:
    """Owns the Charts tab's navigation/filter/option state and detach/export
    orchestration; derives the ``ChartsViewModel`` and pushes it to the bound
    ``ChartsTabView``."""

    def __init__(
        self,
        *,
        gateway: ResultGateway,
        bus: EventBus,
        view_state_store: PerRunViewStateStore,
        theme_manager: ThemeManager | None = None,
        platform_kind: PlatformKind = PlatformKind.UNKNOWN,
    ) -> None:
        self._gateway = gateway
        self._bus = bus
        self._view_state_store = view_state_store
        self._theme_manager = theme_manager
        self._platform_kind = platform_kind
        self._run_id: RunId | None = None
        self._run_mode: RunMode | None = None
        self._view_state: ChartsViewState | None = None
        self._chart_data_cache: dict[ChartKind, ChartData | HeatmapData] = {}
        self._is_terminal = True
        self._view: ChartsTabViewProtocol | None = None
        self._on_drilldown: Callable[[ChartDrilldownRequest], None] | None = None
        logger.debug("charts_tab_controller_constructed")

    def bind(
        self,
        view: ChartsTabViewProtocol,
        *,
        on_drilldown: Callable[[ChartDrilldownRequest], None],
    ) -> None:
        """Attach the bound view and the parent controller's drill-down sink.

        The Charts tab has no owner-bound bus subscription of its own in this
        shell -- ``_chart_data_changed`` wiring is a later story's scope
        (charts_tab.md#14). ``on_drilldown`` is the parent ``ResultController``'s
        ``apply_chart_drilldown`` (charts_tab.md#8) -- a plain callback, matching
        ``FooterController.bind``'s identical parent-callback pattern, since a
        sub-controller never holds a reference to its parent controller directly.
        """
        self._view = view
        self._on_drilldown = on_drilldown
        logger.debug("charts_tab_controller_bound")

    def set_run_context(self, *, run_id: RunId | None, run_mode: RunMode | None) -> None:
        """Re-load the run's Charts view-state slice on a run-selection change (§13)."""
        logger.debug("charts_tab_run_context_set", run_id=run_id, run_mode=run_mode)
        self._run_id = run_id
        self._run_mode = run_mode
        if run_id is None or run_mode is None:
            self._view_state = None
            self._chart_data_cache = {}
            if self._view is not None:
                self._view.apply_no_run("Select a run to view its charts.")
            return
        self._view_state = self._view_state_store.get_slice(
            run_id=run_id,
            slice_key=_SLICE_KEY,
            run_mode=run_mode,
            decoder=decode_view_state,
            default_factory=default_view_state,
        )
        self.recompute_and_push()

    def recompute_and_push(self) -> None:
        """Re-fetch every mode-offered chart's data and push the active chart's
        ``ChartsViewModel`` to the view."""
        if (
            self._view is None
            or self._run_id is None
            or self._run_mode is None
            or self._view_state is None
        ):
            return
        offered = mode_policy.offered_chart_kinds(self._run_mode)
        self._chart_data_cache = {
            kind: self._gateway.chart_data(self._run_id, kind) for kind in offered
        }
        logger.debug(
            "charts_tab_recompute",
            run_id=self._run_id,
            chart_kind=self._view_state.last_chart_kind.value,
            offered_count=len(offered),
        )
        results = self._gateway.list_results(self._run_id)
        tasks = self._gateway.list_tasks(self._run_id)
        tasks_by_id = {task.task_id: task for task in tasks}
        view_model = select_charts_view_model(
            ChartsSelectionInput(
                run_mode=self._run_mode,
                view_state=self._view_state,
                active_kind=self._view_state.last_chart_kind,
                chart_data_cache=self._chart_data_cache,
                results=results,
                tasks_by_id=tasks_by_id,
                is_terminal=self._is_terminal,
            )
        )
        self._view.apply(view_model)

    def on_prev_clicked(self) -> None:
        """Step to the previous mode-offered, populated chart (charts_tab.md#7)."""
        self._navigate(mode_policy.prev_navigable_index)

    def on_next_clicked(self) -> None:
        """Step to the next mode-offered, populated chart (charts_tab.md#7)."""
        self._navigate(mode_policy.next_navigable_index)

    def _navigate(self, index_fn: Callable[..., int | None]) -> None:
        if self._view_state is None or self._run_mode is None:
            return
        offered = mode_policy.offered_chart_kinds(self._run_mode)
        current_index = offered.index(self._view_state.last_chart_kind)
        new_index = index_fn(current_index=current_index, offered=offered, has_data=self._has_data)
        if new_index is None:
            return
        self.on_chart_kind_selected(offered[new_index])

    def _has_data(self, kind: ChartKind) -> bool:
        data = self._chart_data_cache.get(kind)
        return data is not None and data.empty_state_message is None

    def on_chart_kind_selected(self, kind: ChartKind) -> None:
        """Jump directly to a mode-offered chart kind from the dropdown (charts_tab.md#7)."""
        if self._view_state is None:
            return
        logger.debug("charts_tab_kind_selected", chart_kind=kind.value)
        self._update_view_state(msgspec.structs.replace(self._view_state, last_chart_kind=kind))

    def on_filter_changed(self, chip: str, values: tuple[str, ...]) -> None:
        """A global filter chip's selection changed for the active chart kind (§5)."""
        if self._view_state is None or chip not in _CHIP_FIELDS:
            return
        logger.debug("charts_tab_filter_changed", chip=chip, selected_count=len(values))
        self._replace_active_filters({chip: values})

    def on_option_changed(self, key: str, value: str) -> None:
        """A per-chart option control changed for the active chart kind (§6)."""
        if self._view_state is None:
            return
        logger.debug("charts_tab_option_changed", key=key, value=value)
        if key == "drop_outliers":
            self._update_view_state(
                msgspec.structs.replace(self._view_state, outlier_exclusion=value == "true")
            )
            return
        current = filter_state_for(self._view_state, self._view_state.last_chart_kind)
        options = {**current.options, key: value}
        self._replace_active_filters({"options": options}, current=current)

    def on_legend_series_toggled(self, series_name: str) -> None:
        """Hide/show a legend series for the active chart kind (charts 4, 7; §6)."""
        if self._view_state is None:
            return
        logger.debug("charts_tab_legend_series_toggled", series_name=series_name)
        active = self._view_state.last_chart_kind.value
        current = self._view_state.hidden_series_by_kind.get(active, ())
        updated = (
            tuple(s for s in current if s != series_name)
            if series_name in current
            else (*current, series_name)
        )
        hidden_by_kind = {**self._view_state.hidden_series_by_kind, active: updated}
        self._update_view_state(
            msgspec.structs.replace(self._view_state, hidden_series_by_kind=hidden_by_kind)
        )

    def on_clear_filters_clicked(self) -> None:
        """Reset the active chart kind's filters/options to their defaults (§5)."""
        if self._view_state is None:
            return
        logger.debug("charts_tab_clear_filters_clicked")
        active = self._view_state.last_chart_kind.value
        filters_by_kind = {**self._view_state.filters_by_kind}
        filters_by_kind.pop(active, None)
        self._update_view_state(
            msgspec.structs.replace(self._view_state, filters_by_kind=filters_by_kind)
        )

    def on_chart_element_clicked(self, request: ChartDrilldownRequest) -> None:
        """Route a chart-click drill-down request through the parent controller's
        ``on_drilldown`` sink, supplied at ``bind()`` time (charts_tab.md#8)."""
        logger.debug("charts_tab_element_clicked", provider_id=request.provider_id)
        if self._on_drilldown is not None:
            self._on_drilldown(request)

    def render_chart_export(self, *, fmt: str) -> bytes:
        """Render the active chart off-screen as PNG/SVG bytes for the footer's
        export flow (charts_tab.md#12)."""
        tokens = (
            resolve_theme_tokens(
                theme_manager=self._theme_manager, platform_kind=self._platform_kind
            )
            if self._theme_manager is not None
            else make_dark_theme_tokens(platform_kind=self._platform_kind)
        )
        chart_kind = self.current_view_state().last_chart_kind if self._view_state else None
        data = self._chart_data_cache.get(chart_kind) if chart_kind is not None else None
        logger.debug("charts_tab_export_requested", fmt=fmt, chart_kind=chart_kind)
        if chart_kind is None or data is None:
            data = _empty_chart_data()
            chart_kind = ChartKind.AVG_TTFT_PER_MODEL
        if fmt == "svg":
            return painting.render_chart_svg(chart_kind=chart_kind, data=data, tokens=tokens)
        return painting.render_chart_png(chart_kind=chart_kind, data=data, tokens=tokens)

    def set_run_terminal_state(self, *, is_terminal: bool) -> None:
        """Enable/disable this tab's export/detach readiness as the run reaches a
        terminal state (charts_tab.md#12)."""
        self._is_terminal = is_terminal
        if self._view is not None:
            self._view.set_export_enabled(enabled=is_terminal)

    def current_view_state(self) -> ChartsViewState:
        """The currently-active view state; only called once a run is selected."""
        assert self._view_state is not None  # noqa: S101  # narrows for callers post-set_run_context
        return self._view_state

    def _replace_active_filters(
        self, field_updates: dict[str, object], *, current: ChartFilterState | None = None
    ) -> None:
        if self._view_state is None:
            return
        active = self._view_state.last_chart_kind.value
        base = (
            current
            if current is not None
            else filter_state_for(self._view_state, self._view_state.last_chart_kind)
        )
        updated = msgspec.structs.replace(base, **field_updates)
        filters_by_kind = {**self._view_state.filters_by_kind, active: updated}
        self._update_view_state(
            msgspec.structs.replace(self._view_state, filters_by_kind=filters_by_kind)
        )

    def _update_view_state(self, new_state: ChartsViewState) -> None:
        self._view_state = new_state
        if self._run_id is not None:
            self._view_state_store.set_slice(
                run_id=self._run_id,
                slice_key=_SLICE_KEY,
                value=new_state,
                encoder=encode_view_state,
            )
        self.recompute_and_push()


_CHIP_FIELDS = frozenset({"models", "statuses", "verdicts", "categories", "difficulties"})


def _empty_chart_data() -> ChartData:
    return ChartData(chart_kind=ChartKind.AVG_TTFT_PER_MODEL, categories=(), series=())
