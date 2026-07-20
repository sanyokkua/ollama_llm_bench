"""``ResultController`` -- run selection, the user-locked-selection flag, and the
eight Event Bus subscriptions the parent shell owns (STORY-061-AC-1, AC-2, AC-7).

Source of truth: ``docs/v3_specification/05_Result_Widget/description.md`` §6 (run
selection logic), §12 (event-bus integration); ``state_machine.md`` §1 (top-level
states), §2 (run-active overlay), §4 (dropdown auto-jump). Depends only on
``ResultGateway`` plus the retained UI helpers and the widget-local
``PerRunViewStateStore``/``FooterController`` (D-R-06).
"""

from typing import TYPE_CHECKING

import structlog

from ollama_llm_bench.backend.domain import BenchmarkRun, RunId, RunStatus
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
from ollama_llm_bench.ui.results._internal.footer import FooterController
from ollama_llm_bench.ui.results._internal.view_state_store import PerRunViewStateStore
from ollama_llm_bench.ui.results.models import ResultCollaborators, ResultViewModel

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
        self._selected_run_id: RunId | None = None
        self._user_locked = False
        self._active_tab = _DEFAULT_TAB
        self._live = False
        self._live_run_id: RunId | None = None
        self._view: ResultView | None = None
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
        self._push_view_model()

    def _on_run_terminal(self, _payload: object) -> None:
        logger.debug("result_event_received", signal_name="run_terminal")
        self._live = False
        self._live_run_id = None
        self._push_view_model()

    def _push_view_model(self) -> None:
        if self._view is None:
            return
        self._view.apply(self._build_view_model())

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
