"""``DetailsTabController`` -- the Details tab's sub-controller (STORY-063).

Source of truth: ``docs/v3_specification/05_Result_Widget/implementation_structure.md``
§5.2 (concern, subscription, derivation, view-state slice); ``tabs/details_tab.md``
§5 (filter-bar chips), §7 (columns), §8 (sort), §9 (Task Detail Panel), §10
(chart-click drill-down), §15 (persistence), and the ``_detailed_data_changed`` event-bus
integration. Depends only on ``ResultGateway``, the ``EventBus``, and the shared
``PerRunViewStateStore`` (D-R-06) -- never a raw backend Store/Service Protocol.
"""

from typing import Final, Protocol

import msgspec
import structlog

from ollama_llm_bench.backend.domain import RunId, RunMode
from ollama_llm_bench.backend.events import (
    SIGNAL_DETAILED_DATA_CHANGED,
    DetailedDataChangedEvent,
    EventBus,
)
from ollama_llm_bench.ui.results._internal.details_tab import select
from ollama_llm_bench.ui.results._internal.details_tab.select import (
    DetailsChipDomains,
    DetailsColumnKey,
    DetailsSort,
    DetailsViewState,
)
from ollama_llm_bench.ui.results._internal.view_state_store import PerRunViewStateStore
from ollama_llm_bench.ui.results.models import ChartDrilldownRequest, DetailsViewModel
from ollama_llm_bench.ui.results.protocols import ResultGateway

__all__: list[str] = ["DetailsTabController", "DetailsTabViewProtocol"]

logger = structlog.get_logger(__name__)

_SLICE_KEY = "details.view_state"
_SETTING_SCORE_DISPLAY_FORMAT = "ui.score_display_format"

# The seven filter-bar chips map 1:1 onto DetailsFilters' field names (details_tab.md#5).
_CHIP_FIELDS: Final[frozenset[str]] = frozenset(
    {"models", "tasks", "categories", "statuses", "verdicts", "layers", "difficulties"}
)


class DetailsTabViewProtocol(Protocol):
    """The subset of ``DetailsTabView``'s surface this controller drives.

    Declared locally, structurally, because Task 9's ``DetailsTabView`` does not exist
    yet at this controller's build time: a ``TYPE_CHECKING`` forward-reference import
    (the pattern ``SummaryTabController`` uses for its own ``view`` parameter) would
    fail ``mypy --strict`` today since the target module has no implementation to
    resolve. This Protocol keeps ``bind()`` fully typed with zero ``# type: ignore``
    and can be replaced by a forward reference to the concrete ``DetailsTabView`` once
    Task 9 lands, to match the sibling convention.
    """

    def apply(
        self,
        view_model: DetailsViewModel,
        *,
        view_state: DetailsViewState,
        domains: DetailsChipDomains,
    ) -> None:
        """Render the derived ``DetailsViewModel`` against the given view state and
        the seven filter chips' current distinct-value domains."""
        ...

    def apply_no_run(self, message: str) -> None:
        """Render the tab's empty state before any run is selected."""
        ...

    def schedule_recompute(self) -> None:
        """Coalesce a pending recompute triggered by a live-data-changed event."""
        ...

    def set_export_enabled(self, *, enabled: bool) -> None:
        """Enable/disable this tab's export action for the run's terminal state."""
        ...


class DetailsTabController:
    """Owns the Details tab's filters, columns, sort, and row selection; derives the
    ``DetailsViewModel`` and pushes it to the bound ``DetailsTabView``."""

    def __init__(
        self, *, gateway: ResultGateway, bus: EventBus, view_state_store: PerRunViewStateStore
    ) -> None:
        self._gateway = gateway
        self._bus = bus
        self._view_state_store = view_state_store
        self._run_id: RunId | None = None
        self._run_mode: RunMode | None = None
        self._view_state: DetailsViewState | None = None
        self._selected_result_id: int | None = None
        self._view: DetailsTabViewProtocol | None = None
        logger.debug("details_tab_controller_constructed")

    def bind(self, view: DetailsTabViewProtocol) -> None:
        """Subscribe to ``_detailed_data_changed``, owner-bound to ``view``'s lifetime."""
        self._view = view
        self._bus.subscribe(
            SIGNAL_DETAILED_DATA_CHANGED, self._on_detailed_data_changed, owner=view
        )
        logger.debug("details_tab_controller_bound")

    def set_run_context(self, *, run_id: RunId | None, run_mode: RunMode | None) -> None:
        """Re-load the run's Details view-state slice on a run-selection change (§15)."""
        logger.debug("details_tab_run_context_set", run_id=run_id, run_mode=run_mode)
        self._run_id = run_id
        self._run_mode = run_mode
        self._selected_result_id = None
        if run_id is None or run_mode is None:
            self._view_state = None
            if self._view is not None:
                self._view.apply_no_run("Select a run to view its results.")
            return
        self._view_state = self._view_state_store.get_slice(
            run_id=run_id,
            slice_key=_SLICE_KEY,
            run_mode=run_mode,
            decoder=select.decode_view_state,
            default_factory=select.default_view_state,
        )
        self.recompute_and_push()

    def recompute_and_push(self) -> None:
        """Re-derive the ``DetailsViewModel``/Task Detail Panel and push them to the view."""
        if (
            self._view is None
            or self._run_id is None
            or self._run_mode is None
            or self._view_state is None
        ):
            return
        results = self._gateway.list_results(self._run_id)
        tasks = self._gateway.list_tasks(self._run_id)
        tasks_by_id = {task.task_id: task for task in tasks}
        score_display_format = self._gateway.get_setting(_SETTING_SCORE_DISPLAY_FORMAT) or "decimal"
        logger.debug("details_tab_recompute", run_id=self._run_id, result_count=len(results))
        view_model = select.map_details_rows(
            results=results,
            tasks_by_id=tasks_by_id,
            run_mode=self._run_mode,
            view_state=self._view_state,
            score_display_format=score_display_format,
        )
        detail_panel = None
        if self._selected_result_id is not None:
            selected_result = next(
                (r for r in results if r.result_id == self._selected_result_id), None
            )
            if selected_result is not None:
                detail_panel = select.build_detail_panel(
                    result=selected_result,
                    task=tasks_by_id.get(selected_result.task_id),
                    run_mode=self._run_mode,
                )
        view_model = msgspec.structs.replace(
            view_model, selected_result_id=self._selected_result_id, detail_panel=detail_panel
        )
        domains = select.chip_domains(results=results, tasks_by_id=tasks_by_id)
        self._view.apply(view_model, view_state=self._view_state, domains=domains)

    def on_chip_changed(self, chip: str, values: tuple[object, ...]) -> None:
        """A filter-bar chip's selection changed (§5); ``chip`` is one of the seven
        ``DetailsFilters`` field names, and ``values`` replaces that field verbatim."""
        if self._view_state is None or chip not in _CHIP_FIELDS:
            return
        logger.debug("details_tab_chip_changed", chip=chip, selected_count=len(values))
        filters = msgspec.structs.replace(self._view_state.filters, **{chip: values})
        self._update_view_state(msgspec.structs.replace(self._view_state, filters=filters))

    def on_column_filter_changed(self, column: DetailsColumnKey, values: tuple[str, ...]) -> None:
        """A per-column-header filter changed (§7)."""
        if self._view_state is None:
            return
        logger.debug("details_tab_column_filter_changed", column=column.value)
        remaining = tuple(
            entry for entry in self._view_state.filters.column_filters if entry.column != column
        )
        entries = (*remaining, select.ColumnFilterEntry(column=column, allowed_values=values))
        filters = msgspec.structs.replace(self._view_state.filters, column_filters=entries)
        self._update_view_state(msgspec.structs.replace(self._view_state, filters=filters))

    def on_clear_filters_clicked(self) -> None:
        """Reset every chip and per-column filter to 'all selected' (§5)."""
        if self._view_state is None or self._run_mode is None:
            return
        logger.debug("details_tab_clear_filters_clicked")
        default_filters = select.default_view_state(self._run_mode).filters
        self._update_view_state(msgspec.structs.replace(self._view_state, filters=default_filters))

    def on_column_toggled(self, column: DetailsColumnKey, *, visible: bool) -> None:
        """A column's visibility toggle changed inside the Columns popover (§7)."""
        if self._view_state is None:
            return
        if column is DetailsColumnKey.PROVIDER_MODEL and not visible:
            return  # pinned first column; never hideable (§7)
        logger.debug("details_tab_column_toggled", column=column.value, visible=visible)
        current = [c for c in self._view_state.columns.visible if c != column]
        if visible:
            current.append(column)
        columns = msgspec.structs.replace(self._view_state.columns, visible=tuple(current))
        self._update_view_state(msgspec.structs.replace(self._view_state, columns=columns))

    def on_columns_reset_clicked(self) -> None:
        """Restore the mode's default column visibility and order (§7)."""
        if self._view_state is None or self._run_mode is None:
            return
        logger.debug("details_tab_columns_reset_clicked")
        default_columns = select.default_view_state(self._run_mode).columns
        self._update_view_state(msgspec.structs.replace(self._view_state, columns=default_columns))

    def on_columns_reordered(self, new_order: tuple[DetailsColumnKey, ...]) -> None:
        """The user drag-reordered the column headers (§7)."""
        if self._view_state is None:
            return
        logger.debug("details_tab_columns_reordered")
        columns = msgspec.structs.replace(self._view_state.columns, order=new_order)
        self._update_view_state(msgspec.structs.replace(self._view_state, columns=columns))

    def on_sort_header_clicked(self, column: DetailsColumnKey) -> None:
        """Cycle a column header's sort: ascending -> descending -> cleared (§8)."""
        if self._view_state is None:
            return
        logger.debug("details_tab_sort_header_clicked", column=column.value)
        new_sort = _next_sort(self._view_state.sort, column)
        self._update_view_state(msgspec.structs.replace(self._view_state, sort=new_sort))

    def on_row_selected(self, result_id: int | None) -> None:
        """The user clicked a Details-table row, or cleared the selection (§9)."""
        logger.debug("details_tab_row_selected", result_id=result_id)
        self._selected_result_id = result_id
        self.recompute_and_push()

    def apply_drilldown_filter(self, request: ChartDrilldownRequest) -> None:
        """Apply a chart-click drill-down and, for a single-result request, select
        the matching row (§10)."""
        if self._view_state is None or self._run_id is None:
            return
        logger.debug(
            "details_tab_drilldown_applied",
            provider_id=request.provider_id,
            task_id=request.task_id,
        )
        new_state = select.apply_drilldown(self._view_state, request)
        self._update_view_state(new_state)
        if request.task_id is not None:
            matching = next(
                (
                    r
                    for r in self._gateway.list_results(self._run_id)
                    if r.task_id == request.task_id
                ),
                None,
            )
            if matching is not None:
                self.on_row_selected(matching.result_id)

    def get_column_filter_domain(self, column: DetailsColumnKey) -> tuple[str, ...]:
        """Return one column's per-column filter menu domain (§6).

        Always derived from the run's full unfiltered results -- never narrowed by
        any currently-active filter, including that column's own -- so the View can
        query it directly instead of deriving it from its own already-filtered table
        rows (which would self-narrow the menu on repeated use).

        Args:
            column: The column whose filter-menu domain to compute.

        Returns:
            The column's distinct formatted values, or an empty tuple before a run
            is selected.
        """
        if self._run_id is None:
            return ()
        results = self._gateway.list_results(self._run_id)
        tasks = self._gateway.list_tasks(self._run_id)
        tasks_by_id = {task.task_id: task for task in tasks}
        score_display_format = self._gateway.get_setting(_SETTING_SCORE_DISPLAY_FORMAT) or "decimal"
        return select.column_filter_domain(
            results=results,
            tasks_by_id=tasks_by_id,
            column=column,
            score_display_format=score_display_format,
        )

    def set_run_terminal_state(self, *, is_terminal: bool) -> None:
        """Enable/disable this tab's export action as the run reaches a terminal state."""
        if self._view is not None:
            self._view.set_export_enabled(enabled=is_terminal)

    @property
    def current_view_state(self) -> DetailsViewState | None:
        """The currently-active view state, or ``None`` before a run is selected."""
        return self._view_state

    @property
    def current_run_id(self) -> RunId | None:
        """The run id this controller is currently showing, or ``None``."""
        return self._run_id

    def _update_view_state(self, new_state: DetailsViewState) -> None:
        self._view_state = new_state
        if self._run_id is not None:
            self._view_state_store.set_slice(
                run_id=self._run_id,
                slice_key=_SLICE_KEY,
                value=new_state,
                encoder=select.encode_view_state,
            )
        self.recompute_and_push()

    def _on_detailed_data_changed(self, payload: object) -> None:
        if not isinstance(payload, DetailedDataChangedEvent):
            return
        if payload.run_id != self._run_id:
            return
        logger.debug("details_tab_event_received", signal_name="detailed_data_changed")
        if self._view is not None:
            self._view.schedule_recompute()


def _next_sort(current: DetailsSort, column: DetailsColumnKey) -> DetailsSort:
    if current.column != column:
        return DetailsSort(column=column, descending=False)
    if not current.descending:
        return DetailsSort(column=column, descending=True)
    return DetailsSort(column=None, descending=True)
