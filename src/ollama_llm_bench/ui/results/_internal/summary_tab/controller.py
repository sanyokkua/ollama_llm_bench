"""``SummaryTabController`` -- the Summary tab's sub-controller (STORY-062).

Source of truth: ``docs/v3_specification/05_Result_Widget/implementation_structure.md``
§5.1 (concern, subscription, derivation, view-state slice); ``tabs/summary_tab.md`` §6-§8,
§10, §12-§13 (filters, sorting, live update, persistence, event-bus integration). Depends
only on ``ResultGateway``, the ``EventBus``, and the shared ``PerRunViewStateStore``
(D-R-06) -- never a raw backend Store/Service Protocol.
"""

from typing import TYPE_CHECKING

import msgspec
import structlog

from ollama_llm_bench.backend.domain import RunId, RunMode
from ollama_llm_bench.backend.events import (
    SIGNAL_SUMMARY_DATA_CHANGED,
    EventBus,
    SummaryDataChangedEvent,
)
from ollama_llm_bench.ui.results._internal.summary_tab import select
from ollama_llm_bench.ui.results._internal.summary_tab.select import (
    ChipDomains,
    ColumnFilterEntry,
    SummaryColumnKey,
    SummarySort,
    SummaryViewState,
)
from ollama_llm_bench.ui.results._internal.view_state_store import PerRunViewStateStore
from ollama_llm_bench.ui.results.protocols import ResultGateway

if TYPE_CHECKING:
    # Only for the type annotation on `_view` -- view.py imports this module for
    # SummaryTabView's controller reference, so a real module-level import here would
    # be a runtime import cycle (mirrors ui/results/_internal/controller.py).
    from ollama_llm_bench.ui.results._internal.summary_tab.view import SummaryTabView

__all__: list[str] = ["SummaryTabController"]

logger = structlog.get_logger(__name__)

_SLICE_KEY = "summary.view_state"
_SETTING_SCORE_DISPLAY_FORMAT = "ui.score_display_format"


class SummaryTabController:
    """Owns the Summary tab's filters, column layout, and sort; derives the
    aggregate ``SummaryViewModel`` and pushes it to the bound ``SummaryTabView``."""

    def __init__(
        self, *, gateway: ResultGateway, bus: EventBus, view_state_store: PerRunViewStateStore
    ) -> None:
        self._gateway = gateway
        self._bus = bus
        self._view_state_store = view_state_store
        self._run_id: RunId | None = None
        self._run_mode: RunMode | None = None
        self._view_state: SummaryViewState | None = None
        self._last_domains: ChipDomains | None = None
        self._view: SummaryTabView | None = None
        logger.debug("summary_tab_controller_constructed")

    def bind(self, view: "SummaryTabView") -> None:
        """Subscribe to ``_summary_data_changed``, owner-bound to ``view``'s lifetime."""
        self._view = view
        self._bus.subscribe(SIGNAL_SUMMARY_DATA_CHANGED, self._on_summary_data_changed, owner=view)
        logger.debug("summary_tab_controller_bound")

    def set_run_context(self, *, run_id: RunId | None, run_mode: RunMode | None) -> None:
        """Re-load the run's Summary view-state slice on a run-selection change (§13)."""
        logger.debug("summary_tab_run_context_set", run_id=run_id, run_mode=run_mode)
        self._run_id = run_id
        self._run_mode = run_mode
        if run_id is None or run_mode is None:
            self._view_state = None
            if self._view is not None:
                self._view.apply_no_run("Select a run to view its summary.")
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
        """Re-derive the ``SummaryViewModel``/``ChipDomains`` and push them to the view."""
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
        score_display_format = self._gateway.get_setting(_SETTING_SCORE_DISPLAY_FORMAT)
        logger.debug("summary_tab_recompute", run_id=self._run_id, result_count=len(results))
        view_model = select.aggregate_summary(
            results=results,
            tasks_by_id=tasks_by_id,
            run_mode=self._run_mode,
            view_state=self._view_state,
            score_display_format=score_display_format,
        )
        domains = select.chip_domains(results=results, tasks_by_id=tasks_by_id)
        self._last_domains = domains
        visible_columns = _visible_columns_in_order(self._view_state, self._run_mode)
        self._view.apply(
            view_model,
            domains=domains,
            view_state=self._view_state,
            visible_columns=visible_columns,
        )

    def on_chip_changed(self, chip: str, selected_keys: frozenset[str]) -> None:
        """A filter-bar chip's selection changed (§6)."""
        if self._view_state is None:
            return
        logger.debug("summary_tab_chip_changed", chip=chip, selected_count=len(selected_keys))
        filters = self._view_state.filters
        if chip == "models":
            filters = msgspec.structs.replace(filters, models=self._normalize_models(selected_keys))
        elif chip == "verdict":
            filters = msgspec.structs.replace(filters, verdicts=selected_keys)
        elif chip == "difficulty":
            filters = msgspec.structs.replace(filters, difficulties=selected_keys)
        elif chip == "category":
            filters = msgspec.structs.replace(
                filters, categories=self._normalize_categories(selected_keys)
            )
        else:
            return
        self._update_view_state(msgspec.structs.replace(self._view_state, filters=filters))

    def on_column_filter_changed(self, column: SummaryColumnKey, selected: frozenset[str]) -> None:
        """A per-column-header filter changed (§6.1)."""
        if self._view_state is None:
            return
        logger.debug("summary_tab_column_filter_changed", column=column.value)
        remaining = tuple(
            entry for entry in self._view_state.column_filters if entry.column != column
        )
        entries = (*remaining, ColumnFilterEntry(column=column, selected_values=selected))
        self._update_view_state(msgspec.structs.replace(self._view_state, column_filters=entries))

    def on_clear_filters_clicked(self) -> None:
        """Reset every chip and per-column filter to the mode's default (§6)."""
        if self._view_state is None or self._run_mode is None:
            return
        logger.debug("summary_tab_clear_filters_clicked")
        default_filters = select.default_view_state(self._run_mode).filters
        self._update_view_state(
            msgspec.structs.replace(self._view_state, filters=default_filters, column_filters=())
        )

    def on_column_toggled(self, column: SummaryColumnKey, *, visible: bool) -> None:
        """A column's visibility toggle changed inside the Columns popover (§7)."""
        if self._view_state is None:
            return
        if column is SummaryColumnKey.PROVIDER_MODEL and not visible:
            return  # pinned first column; never hideable (§7)
        logger.debug("summary_tab_column_toggled", column=column.value, visible=visible)
        current = set(self._view_state.layout.visible)
        current.add(column) if visible else current.discard(column)
        layout = msgspec.structs.replace(self._view_state.layout, visible=frozenset(current))
        self._update_view_state(msgspec.structs.replace(self._view_state, layout=layout))

    def on_columns_reset_clicked(self) -> None:
        """Restore the mode's default column visibility (§7)."""
        if self._view_state is None or self._run_mode is None:
            return
        logger.debug("summary_tab_columns_reset_clicked")
        default_layout = select.default_view_state(self._run_mode).layout
        self._update_view_state(msgspec.structs.replace(self._view_state, layout=default_layout))

    def on_columns_reordered(self, new_order: tuple[SummaryColumnKey, ...]) -> None:
        """The user drag-reordered the column headers (§7)."""
        if self._view_state is None:
            return
        logger.debug("summary_tab_columns_reordered")
        layout = msgspec.structs.replace(self._view_state.layout, order=new_order)
        self._update_view_state(msgspec.structs.replace(self._view_state, layout=layout))

    def on_sort_header_clicked(self, column: SummaryColumnKey) -> None:
        """Cycle a column header's sort: ascending -> descending -> cleared (§8)."""
        if self._view_state is None:
            return
        logger.debug("summary_tab_sort_header_clicked", column=column.value)
        new_sort = _next_sort(self._view_state.sort, column)
        self._update_view_state(msgspec.structs.replace(self._view_state, sort=new_sort))

    @property
    def current_view_state(self) -> SummaryViewState | None:
        """The currently-active view state, or ``None`` before a run is selected."""
        return self._view_state

    @property
    def current_run_id(self) -> RunId | None:
        """The run id this controller is currently showing, or ``None``."""
        return self._run_id

    def _normalize_models(self, selected: frozenset[str]) -> frozenset[str] | None:
        if self._last_domains is None:
            return selected
        full_domain = frozenset(key for key, _ in self._last_domains.models)
        return None if selected == full_domain else selected

    def _normalize_categories(self, selected: frozenset[str]) -> frozenset[str] | None:
        if self._last_domains is None:
            return selected
        full_domain = frozenset(self._last_domains.categories)
        return None if selected == full_domain else selected

    def _update_view_state(self, new_state: SummaryViewState) -> None:
        self._view_state = new_state
        if self._run_id is not None:
            self._view_state_store.set_slice(
                run_id=self._run_id,
                slice_key=_SLICE_KEY,
                value=new_state,
                encoder=select.encode_view_state,
            )
        self.recompute_and_push()

    def _on_summary_data_changed(self, payload: object) -> None:
        if not isinstance(payload, SummaryDataChangedEvent):
            return
        if payload.run_id != self._run_id:
            return
        logger.debug("summary_tab_event_received", signal_name="summary_data_changed")
        if self._view is not None:
            self._view.schedule_recompute()


def _visible_columns_in_order(
    view_state: SummaryViewState, run_mode: RunMode
) -> tuple[SummaryColumnKey, ...]:
    offered = select.offered_columns(run_mode)
    return tuple(
        column
        for column in view_state.layout.order
        if column in view_state.layout.visible and column in offered
    )


def _next_sort(current: SummarySort, column: SummaryColumnKey) -> SummarySort:
    if current.column != column:
        return SummarySort(column=column, descending=False)
    if not current.descending:
        return SummarySort(column=column, descending=True)
    return SummarySort(column=None, descending=True)
