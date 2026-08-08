"""``ResultController`` -- run selection, the user-locked-selection flag, and the
eight Event Bus subscriptions the parent shell owns (STORY-061-AC-1, AC-2, AC-7).

Source of truth: ``docs/v3_specification/05_Result_Widget/description.md`` §6 (run
selection logic), §12 (event-bus integration); ``state_machine.md`` §1 (top-level
states), §2 (run-active overlay), §4 (dropdown auto-jump). Depends only on
``ResultGateway`` plus the retained UI helpers and the widget-local
``PerRunViewStateStore``/``FooterController`` (D-R-06).
"""

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QVBoxLayout
import structlog

from ollama_llm_bench.backend.domain import BenchmarkRun, ChartKind, RunId, RunMode, RunStatus
from ollama_llm_bench.backend.events import (
    SIGNAL_RUN_FAILED,
    SIGNAL_RUN_FINISHED,
    SIGNAL_RUN_ID_CHANGED,
    SIGNAL_RUN_LIST_CHANGED,
    SIGNAL_RUN_RENAMED,
    SIGNAL_RUN_STARTED,
    SIGNAL_RUN_STOPPED,
    RunIdChangedEvent,
    RunStartedEvent,
)
from ollama_llm_bench.ui.results._internal.charts_tab.controller import ChartsTabController
from ollama_llm_bench.ui.results._internal.charts_tab.detached_window import (
    DetachedChartWindow,
    DetachedChartWindowConfig,
)
from ollama_llm_bench.ui.results._internal.charts_tab.view import ChartsTabView
from ollama_llm_bench.ui.results._internal.details_tab.controller import DetailsTabController
from ollama_llm_bench.ui.results._internal.details_tab.view import DetailsTabView
from ollama_llm_bench.ui.results._internal.footer import FooterController
from ollama_llm_bench.ui.results._internal.run_analysis_tab.controller import (
    JudgeAnalysisTabController,
)
from ollama_llm_bench.ui.results._internal.run_analysis_tab.view import JudgeAnalysisTabView
from ollama_llm_bench.ui.results._internal.summary_tab.controller import SummaryTabController
from ollama_llm_bench.ui.results._internal.summary_tab.view import SummaryTabView
from ollama_llm_bench.ui.results._internal.view_state_store import PerRunViewStateStore
from ollama_llm_bench.ui.results.models import (
    ChartDrilldownRequest,
    ResultCollaborators,
    ResultViewModel,
)

if TYPE_CHECKING:
    # Only for the type annotation on `_view` -- view.py imports this module for
    # ResultView's controller reference, so a real module-level import here would
    # be a runtime import cycle.
    from ollama_llm_bench.ui.results._internal.view import ResultView

__all__: list[str] = ["ResultController"]

logger = structlog.get_logger(__name__)

_SETTING_LAST_RESULT_TAB = "ui.last_result_tab"
_DEFAULT_TAB = "summary"


class ResultController:
    """Owns the selected run id, the user-locked-selection flag, the active tab,
    and the orthogonal ``live`` flag; constructs the ``PerRunViewStateStore`` and
    the ``FooterController``."""

    def __init__(self, *, collaborators: ResultCollaborators) -> None:
        self._collaborators = collaborators
        self.view_state_store = PerRunViewStateStore(gateway=collaborators.gateway)
        self._footer = FooterController(collaborators=collaborators)
        self._summary_tab = SummaryTabController(
            gateway=collaborators.gateway,
            bus=collaborators.bus,
            view_state_store=self.view_state_store,
        )
        self._details_tab = DetailsTabController(
            gateway=collaborators.gateway,
            bus=collaborators.bus,
            view_state_store=self.view_state_store,
        )
        self._charts_tab = ChartsTabController(
            gateway=collaborators.gateway,
            bus=collaborators.bus,
            view_state_store=self.view_state_store,
            platform_kind=collaborators.platform_kind,
        )
        self._footer.set_chart_export_source(self._charts_tab)
        self._run_analysis_tab = JudgeAnalysisTabController(
            gateway=collaborators.gateway,
            bus=collaborators.bus,
            clipboard=collaborators.clipboard,
        )
        self._selected_run_id: RunId | None = None
        self._user_locked = False
        self._active_tab = _DEFAULT_TAB
        self._live = False
        self._live_run_id: RunId | None = None
        self._view: ResultView | None = None
        self._summary_tab_context: tuple[RunId | None, RunMode | None] = (None, None)
        self._details_tab_context: tuple[RunId | None, RunMode | None] = (None, None)
        self._charts_tab_context: tuple[RunId | None, RunMode | None] = (None, None)
        self._run_analysis_tab_context: RunId | None = None
        logger.debug("result_controller_constructed")

    def bind(self, view: "ResultView") -> None:
        """Subscribe to the Event Bus, owner-bound to ``view``'s lifetime."""
        self._view = view
        bus = self._collaborators.bus
        bus.subscribe(SIGNAL_RUN_LIST_CHANGED, self._on_run_list_changed, owner=view)
        bus.subscribe(SIGNAL_RUN_ID_CHANGED, self._on_external_run_id_changed, owner=view)
        bus.subscribe(SIGNAL_RUN_RENAMED, self._on_run_renamed, owner=view)
        bus.subscribe(SIGNAL_RUN_STARTED, self._on_run_started, owner=view)
        bus.subscribe(SIGNAL_RUN_FINISHED, self._on_run_terminal, owner=view)
        bus.subscribe(SIGNAL_RUN_STOPPED, self._on_run_terminal, owner=view)
        bus.subscribe(SIGNAL_RUN_FAILED, self._on_run_terminal, owner=view)
        self._footer.bind(view, on_view_model_changed=self._on_footer_view_model_changed)
        self._mount_summary_tab(view)
        self._mount_details_tab(view)
        self._mount_charts_tab(view)
        self._mount_run_analysis_tab(view)

    def _mount_summary_tab(self, view: "ResultView") -> None:
        summary_view = SummaryTabView(platform_kind=self._collaborators.platform_kind)
        host = view.tab_host("summary")
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(summary_view)
        summary_view.bind_controller(self._summary_tab)
        self._summary_tab.bind(summary_view)

    def _mount_details_tab(self, view: "ResultView") -> None:
        details_view = DetailsTabView(platform_kind=self._collaborators.platform_kind)
        host = view.tab_host("details")
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(details_view)
        details_view.bind_controller(self._details_tab)
        self._details_tab.bind(details_view)

    def _mount_run_analysis_tab(self, view: "ResultView") -> None:
        judge_view = JudgeAnalysisTabView(platform_kind=self._collaborators.platform_kind)
        host = view.tab_host("run_analysis")
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(judge_view)
        judge_view.bind_controller(self._run_analysis_tab)
        judge_view.generate_clicked.connect(self._on_run_analysis_generate_clicked)
        self._run_analysis_tab.bind(judge_view)

    def _on_run_analysis_generate_clicked(self) -> None:
        run_id = self._selected_run_id
        if run_id is None:
            return
        # Deferred import (mirrors ui.new_benchmark/ui.resume_benchmark's own
        # established precedent): every other consumer of ui.common_dialogs defers
        # this import to first-use rather than module scope, breaking a transitive
        # import-cycle risk through ui.new_benchmark, which ui.common_dialogs also
        # imports from.
        from ollama_llm_bench.ui.common_dialogs import (  # noqa: PLC0415
            GenerateAnalysisCollaborators,
            make_generate_analysis_dialog,
        )

        run = self._collaborators.gateway.get_run(run_id)
        dialog = make_generate_analysis_dialog(
            run=run,
            collaborators=GenerateAnalysisCollaborators(
                dispatcher=self._run_analysis_tab,
                provider_source=self._collaborators.provider_source,
                model_fetcher=self._collaborators.model_fetcher,
                event_bus=self._collaborators.bus,
            ),
            parent=self._view,
        )
        dialog.exec()

    def _mount_charts_tab(self, view: "ResultView") -> None:
        charts_view = ChartsTabView(platform_kind=self._collaborators.platform_kind)
        host = view.tab_host("charts")
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(charts_view)
        charts_view.prev_clicked.connect(self._charts_tab.on_prev_clicked)
        charts_view.next_clicked.connect(self._charts_tab.on_next_clicked)
        charts_view.chart_kind_selected.connect(
            lambda value: self._charts_tab.on_chart_kind_selected(ChartKind(value))
        )
        charts_view.filter_changed.connect(
            lambda chip, values: self._charts_tab.on_filter_changed(chip, tuple(values))
        )
        charts_view.option_changed.connect(self._charts_tab.on_option_changed)
        charts_view.legend_series_toggled.connect(self._charts_tab.on_legend_series_toggled)
        charts_view.clear_filters_clicked.connect(self._charts_tab.on_clear_filters_clicked)
        charts_view.chart_element_clicked.connect(self._charts_tab.on_chart_element_clicked)
        charts_view.detach_clicked.connect(self._on_charts_detach_clicked)
        self._charts_tab.bind(charts_view, on_drilldown=self.apply_chart_drilldown)

    def _on_charts_detach_clicked(self) -> None:
        run_id = self._selected_run_id
        if run_id is None:
            return
        run_mode = self._collaborators.gateway.get_run(run_id).run_mode
        window = DetachedChartWindow(
            config=DetachedChartWindowConfig(
                gateway=self._collaborators.gateway,
                bus=self._collaborators.bus,
                run_id=run_id,
                run_mode=run_mode,
                initial_state=self._charts_tab.current_view_state(),
                platform_kind=self._collaborators.platform_kind,
                on_drilldown=self.apply_chart_drilldown,
            ),
            parent=self._view,
        )
        window.show()

    def load_initial_state(self) -> None:
        """Resolve the ``Loading`` state on mount (state_machine.md §1)."""
        stored_tab = self._collaborators.gateway.get_setting(_SETTING_LAST_RESULT_TAB)
        self._active_tab = stored_tab or _DEFAULT_TAB
        runs = self._collaborators.gateway.list_runs()
        if runs:
            self._selected_run_id = _newest(runs).run_id
        live_run = next((run for run in runs if run.status == RunStatus.INCOMPLETE), None)
        if live_run is not None:
            self._live = True
            self._live_run_id = live_run.run_id
        logger.debug(
            "result_initial_state_loaded",
            selected_run_id=self._selected_run_id,
            active_tab=self._active_tab,
            live=self._live,
        )
        self._details_tab.set_run_terminal_state(is_terminal=not self._live)
        self._charts_tab.set_run_terminal_state(is_terminal=not self._live)
        self._run_analysis_tab.set_run_terminal_state(is_terminal=not self._live)
        self._push_view_model()

    def on_dropdown_changed(self, run_id: RunId) -> None:
        """A user-driven run-selector change; emits ``_run_id_changed`` (AC-2)."""
        if run_id == self._selected_run_id:
            return
        previous = self._selected_run_id
        self._selected_run_id = run_id
        self._user_locked = run_id != self._live_run_id
        logger.debug("result_dropdown_changed", run_id=run_id, user_locked=self._user_locked)
        self._push_view_model()
        self._collaborators.bus.emit(
            SIGNAL_RUN_ID_CHANGED, RunIdChangedEvent(run_id=run_id, previous_run_id=previous)
        )

    def on_tab_changed(self, tab: str) -> None:
        """A tab-strip click; persists ``ui.last_result_tab`` (§4)."""
        self._active_tab = tab
        self._collaborators.gateway.set_setting(_SETTING_LAST_RESULT_TAB, tab)
        logger.debug("result_tab_changed", active_tab=tab)
        self._push_view_model()

    def on_export_clicked(self, button_label: str) -> None:
        """Forward a footer export-button click to the ``FooterController``."""
        self._footer.on_export_clicked(button_label)

    def on_save_directly_toggled(self, checked: bool) -> None:  # noqa: FBT001  # Qt signal payload
        """Forward the save-destination toggle to the ``FooterController``."""
        self._footer.on_save_directly_toggled(checked=checked)
        self._push_view_model()

    def on_open_exports_folder_clicked(self) -> None:
        """Forward the Open-Exports-Folder click to the ``FooterController``."""
        self._footer.on_open_exports_folder_clicked()

    def current_selected_run_id(self) -> RunId | None:
        """The run id currently tracked as selected (read by tests and, later,
        a sibling widget wanting the current selection without an event round-trip)."""
        return self._selected_run_id

    def apply_chart_drilldown(self, request: ChartDrilldownRequest) -> None:
        """In-process chart-click drill-down entry point (details_tab.md §10).

        Switches the visible tab to Details and applies the drill-down filter --
        not an Event Bus signal; the (future, STORY-064) Charts tab controller calls
        this directly on the mounted ``ResultController``.
        """
        logger.debug("result_controller_drilldown_received", provider_id=request.provider_id)
        self.on_tab_changed("details")
        self._details_tab.apply_drilldown_filter(request)

    def _on_footer_view_model_changed(self, _footer_vm: object) -> None:
        # Another footer instance changed the shared setting; rebuild the full
        # ResultViewModel so this widget's own footer stays in sync (EC-WS-1).
        self._push_view_model()

    def _on_run_list_changed(self, _payload: object) -> None:
        logger.debug("result_event_received", signal_name="run_list_changed")
        runs = self._collaborators.gateway.list_runs()
        if not any(run.run_id == self._selected_run_id for run in runs):
            self._selected_run_id = _newest(runs).run_id if runs else None
        self._push_view_model()

    def _on_external_run_id_changed(self, payload: object) -> None:
        if not isinstance(payload, RunIdChangedEvent):
            return
        if payload.run_id == self._selected_run_id:
            return
        logger.debug("result_event_received", signal_name="run_id_changed", run_id=payload.run_id)
        self._selected_run_id = payload.run_id
        self._push_view_model()

    def _on_run_renamed(self, _payload: object) -> None:
        logger.debug("result_event_received", signal_name="run_renamed")
        self._push_view_model()

    def _on_run_started(self, payload: object) -> None:
        if not isinstance(payload, RunStartedEvent):
            return
        logger.debug("result_event_received", signal_name="run_started", run_id=payload.run_id)
        self._live = True
        self._live_run_id = payload.run_id
        if not self._user_locked:
            self._selected_run_id = payload.run_id
        self._details_tab.set_run_terminal_state(is_terminal=False)
        self._charts_tab.set_run_terminal_state(is_terminal=False)
        self._run_analysis_tab.set_run_terminal_state(is_terminal=False)
        self._push_view_model()

    def _on_run_terminal(self, _payload: object) -> None:
        logger.debug("result_event_received", signal_name="run_terminal")
        self._live = False
        self._live_run_id = None
        self._details_tab.set_run_terminal_state(is_terminal=True)
        self._charts_tab.set_run_terminal_state(is_terminal=True)
        self._run_analysis_tab.set_run_terminal_state(is_terminal=True)
        self._push_view_model()
        # `_push_view_model`'s three `_sync_*_tab` calls are change-detected on
        # `(run_id, run_mode)`, which `_on_run_started` already set to this very
        # run -- so they no-op here and the tables would still show the empty
        # state they had at run start. `set_run_terminal_state` only toggles the
        # export button. These three calls are what actually re-read the now-
        # persisted rows.
        #
        # Deliberately NOT done by clearing `_details_tab_context` to defeat the
        # change detection: that routes back through `set_run_context`, which
        # resets `_selected_result_id` to `None`, so a user who had a row
        # selected while the run finished would lose their selection.
        self._summary_tab.recompute_and_push()
        self._details_tab.recompute_and_push()
        self._charts_tab.recompute_and_push()

    def _push_view_model(self) -> None:
        self._sync_summary_tab()
        self._sync_details_tab()
        self._sync_charts_tab()
        self._sync_run_analysis_tab()
        if self._view is None:
            return
        self._view.apply(self._build_view_model())

    def _sync_summary_tab(self) -> None:
        """Re-load the Summary tab's run context whenever the selected run changes.

        The single choke-point every ``_selected_run_id``-affecting event routes
        through (``load_initial_state``, ``on_dropdown_changed``,
        ``_on_run_list_changed``, ``_on_external_run_id_changed``,
        ``_on_run_started``) -- avoids duplicating this call at each of those sites.
        """
        run_mode = (
            self._collaborators.gateway.get_run(self._selected_run_id).run_mode
            if self._selected_run_id is not None
            else None
        )
        context = (self._selected_run_id, run_mode)
        if context == self._summary_tab_context:
            return
        self._summary_tab_context = context
        self._summary_tab.set_run_context(run_id=self._selected_run_id, run_mode=run_mode)

    def _sync_details_tab(self) -> None:
        """Re-load the Details tab's run context whenever the selected run changes.

        Mirrors ``_sync_summary_tab``'s change-detection choke-point exactly.
        """
        run_mode = (
            self._collaborators.gateway.get_run(self._selected_run_id).run_mode
            if self._selected_run_id is not None
            else None
        )
        context = (self._selected_run_id, run_mode)
        if context == self._details_tab_context:
            return
        self._details_tab_context = context
        self._details_tab.set_run_context(run_id=self._selected_run_id, run_mode=run_mode)

    def _sync_charts_tab(self) -> None:
        """Re-load the Charts tab's run context whenever the selected run changes.

        Mirrors ``_sync_summary_tab``'s change-detection choke-point exactly.
        """
        run_mode = (
            self._collaborators.gateway.get_run(self._selected_run_id).run_mode
            if self._selected_run_id is not None
            else None
        )
        context = (self._selected_run_id, run_mode)
        if context == self._charts_tab_context:
            return
        self._charts_tab_context = context
        self._charts_tab.set_run_context(run_id=self._selected_run_id, run_mode=run_mode)

    def _sync_run_analysis_tab(self) -> None:
        """Re-load the Run Analysis tab's run context whenever the selected run
        changes. Mirrors ``_sync_summary_tab``'s change-detection choke-point --
        this tab needs only ``run_id``, not ``run_mode`` (§12: no per-mode view
        state)."""
        if self._selected_run_id == self._run_analysis_tab_context:
            return
        self._run_analysis_tab_context = self._selected_run_id
        self._run_analysis_tab.set_run_context(run_id=self._selected_run_id)

    def _build_view_model(self) -> ResultViewModel:
        runs = self._collaborators.gateway.list_runs()
        widget_state = "run_selected" if runs else "no_run"
        run_options = tuple(
            (run.run_id, _effective_run_name(run)) for run in _sorted_newest_first(runs)
        )
        footer_vm = self._footer.set_context(
            run_id=self._selected_run_id, active_tab=self._active_tab, live=self._live
        )
        return ResultViewModel(
            widget_state=widget_state,
            run_options=run_options,
            selected_run_id=self._selected_run_id,
            active_tab=self._active_tab,
            footer=footer_vm,
        )


def _sorted_newest_first(runs: tuple[BenchmarkRun, ...]) -> tuple[BenchmarkRun, ...]:
    return tuple(sorted(runs, key=lambda run: run.run_id, reverse=True))


def _newest(runs: tuple[BenchmarkRun, ...]) -> BenchmarkRun:
    return _sorted_newest_first(runs)[0]


def _effective_run_name(run: BenchmarkRun) -> str:
    """The user-set name if present, otherwise a minimal generated fallback.

    A simplified stand-in for the full default-name template (SPEC-077, owned by
    ``ui/resume_benchmark``'s ``default_run_name``); this shell only needs a
    stable, non-empty dropdown label.
    """
    return run.run_name or f"Run {run.run_id}"
