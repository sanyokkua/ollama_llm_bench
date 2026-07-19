"""``ResumeBenchmarkController`` -- EventBus subscriptions, selection, sort persistence
(STORY-056-AC-2). Depends only on ``ResumeGateway`` plus ``EventBus``, ``NativePickers``,
and ``FileSystemActions`` -- never a raw backend Store/Service Protocol (D-R-06).
"""

from functools import partial
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QMenu, QWidget
import structlog

from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.adapters.native_pickers import NativePickers
from ollama_llm_bench.backend.domain import RunId
from ollama_llm_bench.backend.events import (
    SIGNAL_RUN_ANALYSIS_RECEIVED,
    SIGNAL_RUN_FAILED,
    SIGNAL_RUN_FINISHED,
    SIGNAL_RUN_ID_CHANGED,
    SIGNAL_RUN_LIST_CHANGED,
    SIGNAL_RUN_RENAMED,
    SIGNAL_RUN_STARTED,
    SIGNAL_RUN_STOPPED,
    SIGNAL_TASK_FILE_CHANGED,
    EventBus,
    RunAnalysisReceivedEvent,
    RunFailedEvent,
    RunFinishedEvent,
    RunIdChangedEvent,
    RunRenamedEvent,
    RunStartedEvent,
    RunStoppedEvent,
)
from ollama_llm_bench.ui.resume_benchmark._internal.actions import (
    clone_as_new_retry_run,
    confirm_and_delete_run,
    export_run_analysis,
    export_table_not_yet_available,
    show_run_log_file,
)
from ollama_llm_bench.ui.resume_benchmark._internal.context_menu import build_context_menu
from ollama_llm_bench.ui.resume_benchmark._internal.run_table_model import (
    COL_MODE,
    COL_NAME,
    COL_STARTED,
    COL_STATUS,
    COL_TASKS,
    RunTableModel,
)
from ollama_llm_bench.ui.resume_benchmark._internal.view_model_select import (
    default_run_name,
    select_run_rows,
)
from ollama_llm_bench.ui.resume_benchmark.models import RunRow
from ollama_llm_bench.ui.resume_benchmark.protocols import ResumeGateway

if TYPE_CHECKING:
    # Only for the cast() in _push_resume_button_state -- view.py imports this
    # module for ResumeBenchmarkView's constructor parameter, so a real
    # module-level import here would be a runtime import cycle.
    from ollama_llm_bench.ui.resume_benchmark._internal.view import ResumeBenchmarkView

__all__: list[str] = ["ResumeBenchmarkController"]

logger = structlog.get_logger(__name__)

_COLUMN_NAMES: dict[int, str] = {
    COL_NAME: "name",
    COL_MODE: "mode",
    COL_STARTED: "started",
    COL_STATUS: "status",
    COL_TASKS: "tasks",
}
_COLUMN_BY_NAME: dict[str, int] = {name: column for column, name in _COLUMN_NAMES.items()}
_EXPORT_TABLE_ACTION_NAMES = frozenset(
    {
        "action_export_summary_csv",
        "action_export_summary_md",
        "action_export_details_csv",
        "action_export_details_md",
    }
)
_RUN_TOUCHED_EVENT_TYPES = (
    RunRenamedEvent,
    RunStartedEvent,
    RunFinishedEvent,
    RunStoppedEvent,
    RunFailedEvent,
    RunAnalysisReceivedEvent,
)


class ResumeBenchmarkController:
    """Owns the Resume Benchmark widget's run table state: subscribes, derives, applies."""

    def __init__(
        self,
        *,
        gateway: ResumeGateway,
        event_bus: EventBus,
        native_pickers: NativePickers,
        file_system_actions: FileSystemActions,
    ) -> None:
        self._gateway = gateway
        self._event_bus = event_bus
        self._native_pickers = native_pickers
        self._file_system_actions = file_system_actions
        self.table_model = RunTableModel()
        self._current_rows: tuple[RunRow, ...] = ()
        self._selected_run_id: RunId | None = None
        self._view: QWidget | None = None
        logger.debug("resume_controller_constructed")

    def bind(self, view: QWidget) -> None:
        """Subscribe to the Event Bus, owner-bound to ``view``'s lifetime."""
        self._view = view
        self._event_bus.subscribe(SIGNAL_RUN_LIST_CHANGED, self._on_run_list_changed, owner=view)
        self._event_bus.subscribe(SIGNAL_RUN_RENAMED, self._on_run_touched, owner=view)
        self._event_bus.subscribe(
            SIGNAL_RUN_ID_CHANGED, self._on_external_run_id_changed, owner=view
        )
        self._event_bus.subscribe(SIGNAL_RUN_STARTED, self._on_run_touched, owner=view)
        self._event_bus.subscribe(SIGNAL_RUN_FINISHED, self._on_run_touched, owner=view)
        self._event_bus.subscribe(SIGNAL_RUN_STOPPED, self._on_run_touched, owner=view)
        self._event_bus.subscribe(SIGNAL_RUN_FAILED, self._on_run_touched, owner=view)
        self._event_bus.subscribe(SIGNAL_RUN_ANALYSIS_RECEIVED, self._on_run_touched, owner=view)
        self._event_bus.subscribe(SIGNAL_TASK_FILE_CHANGED, self._on_task_file_changed, owner=view)

    def load_initial_rows(self) -> None:
        """Restore the persisted sort, then build and apply the initial rows."""
        column_name, descending = self._gateway.get_sort_setting()
        column = _COLUMN_BY_NAME.get(column_name, COL_STARTED)
        self.table_model.set_sort(column, descending=descending)
        self._rebuild_all_rows()

    def on_row_selected(self, run_id: RunId | None) -> None:
        """A user table-selection change; emits ``_run_id_changed``."""
        previous = self._selected_run_id
        self._selected_run_id = run_id
        logger.debug("resume_row_selected", run_id=run_id)
        self._event_bus.emit(
            SIGNAL_RUN_ID_CHANGED, RunIdChangedEvent(run_id=run_id, previous_run_id=previous)
        )
        self._push_resume_button_state()

    def on_search_term_changed(self, term: str) -> None:
        """The search box's debounced text change; re-filters and may clear selection."""
        self.table_model.set_search_term(term)
        self._clear_selection_if_filtered_out()

    def on_sort_header_clicked(self, column: int) -> None:
        """A column-header click; toggles/sets sort, then persists it."""
        descending = (
            not self.table_model.sort_descending if column == self.table_model.sort_column else True
        )
        self.table_model.set_sort(column, descending=descending)
        self._gateway.set_sort_setting(_COLUMN_NAMES[column], descending)

    def on_context_menu_requested(self, view_row: int, global_pos: QPoint) -> None:
        """Build and exec the grouped context menu for the row at ``view_row``."""
        if self._view is None:
            return
        row = self.table_model.visible_row(view_row)
        menu = build_context_menu(row=row, parent=self._view)
        self._wire_menu_actions(menu, row)
        menu.exec(global_pos)

    def on_pencil_clicked(self, view_row: int) -> None:
        """The inline pencil Icon Button click; opens Rename for that row (§3.3)."""
        row = self.table_model.visible_row(view_row)
        logger.debug("resume_pencil_clicked", run_id=row.run_id)
        self._on_rename_triggered(row.run_id)

    def on_more_clicked(self, view_row: int, global_pos: QPoint) -> None:
        """The inline ⋯ Icon Button click; opens the same context menu (SPEC-078)."""
        logger.debug("resume_more_clicked", view_row=view_row)
        self.on_context_menu_requested(view_row, global_pos)

    def current_selected_run_id(self) -> RunId | None:
        """The run id currently tracked as selected.

        Read by the view to restore the ``QTableView``'s visual selection
        after a model reset (``set_rows``/``set_search_term``/``set_sort``
        all clear Qt's own selection model).
        """
        return self._selected_run_id

    def _wire_menu_actions(self, menu: QMenu, row: RunRow) -> None:
        for action in menu.actions():
            name = action.objectName()
            if name == "action_clone":
                action.triggered.connect(partial(self._on_clone_triggered, row.run_id))
            elif name == "action_rename":
                action.triggered.connect(partial(self._on_rename_triggered, row.run_id))
            elif name == "action_delete":
                action.triggered.connect(partial(self._on_delete_triggered, row))
            elif name == "action_export_analysis":
                action.triggered.connect(partial(self._on_export_analysis_triggered, row))
            elif name == "action_show_log":
                action.triggered.connect(partial(self._on_show_log_triggered, row))
            elif name == "action_retry":
                action.triggered.connect(partial(self._on_retry_triggered, row.run_id))
            elif name in _EXPORT_TABLE_ACTION_NAMES:
                action.triggered.connect(self._on_export_table_triggered)

    def _on_clone_triggered(self, source_run_id: RunId) -> None:
        logger.debug("resume_clone_triggered", source_run_id=source_run_id)
        new_run_id = clone_as_new_retry_run(gateway=self._gateway, source_run_id=source_run_id)
        self._rebuild_all_rows()
        self.on_row_selected(new_run_id)

    def _on_rename_triggered(self, run_id: RunId) -> None:
        # Deferred import: ui.common_dialogs needs ui.resume_benchmark.protocols
        # (RunSummaryGateway-style structural fakes elsewhere) at import time via
        # ui.new_benchmark; a module-level import here would re-enter that chain
        # before it finishes initialising, exactly the documented cycle
        # ui.new_benchmark._internal.controller._on_start_clicked already breaks
        # the same way.
        from ollama_llm_bench.ui.common_dialogs import make_rename_run_dialog  # noqa: PLC0415

        if self._view is None:
            return
        logger.debug("resume_rename_triggered", run_id=run_id)
        current_custom_name, computed_default_name = self.rename_context_for(run_id)
        dialog = make_rename_run_dialog(
            gateway=self._gateway,
            run_id=run_id,
            current_custom_name=current_custom_name,
            computed_default_name=computed_default_name,
            parent=self._view,
        )
        dialog.exec()

    def _on_delete_triggered(self, row: RunRow) -> None:
        if self._view is None:
            return
        confirm_and_delete_run(
            gateway=self._gateway,
            event_bus=self._event_bus,
            run_id=row.run_id,
            run_name=row.effective_name,
            parent=self._view,
        )
        self._rebuild_all_rows()

    def on_resume_run_clicked(self) -> None:
        """The footer Resume Run button click; opens the Resume Summary dialog."""
        # Deferred import: see _on_rename_triggered's docstring note for why
        # ui.common_dialogs is imported here rather than at module scope.
        from ollama_llm_bench.ui.common_dialogs import make_resume_summary_dialog  # noqa: PLC0415

        if self._view is None or self._selected_run_id is None:
            return
        run_id = self._selected_run_id
        logger.debug("resume_run_clicked", run_id=run_id)
        dialog = make_resume_summary_dialog(
            gateway=self._gateway, event_bus=self._event_bus, run_id=run_id, parent=self._view
        )
        if dialog is None:
            return
        dialog.exec()
        self._rebuild_all_rows()

    def _on_retry_triggered(self, run_id: RunId) -> None:
        from ollama_llm_bench.ui.common_dialogs import make_retry_selection_dialog  # noqa: PLC0415

        if self._view is None:
            return
        logger.debug("resume_retry_triggered", run_id=run_id)
        dialog = make_retry_selection_dialog(
            gateway=self._gateway, run_id=run_id, parent=self._view
        )
        if dialog is None:
            return
        dialog.exec()
        self._rebuild_all_rows()

    def _on_export_table_triggered(self) -> None:
        export_table_not_yet_available(event_bus=self._event_bus)

    def _on_export_analysis_triggered(self, row: RunRow) -> None:
        export_run_analysis(
            gateway=self._gateway,
            native_pickers=self._native_pickers,
            event_bus=self._event_bus,
            run_id=row.run_id,
            effective_run_name=row.effective_name,
        )

    def _on_show_log_triggered(self, row: RunRow) -> None:
        run = self._gateway.get_run(row.run_id)
        show_run_log_file(
            file_system_actions=self._file_system_actions,
            event_bus=self._event_bus,
            run_id=row.run_id,
            started_at=run.started_at or "",
        )

    def _on_run_list_changed(self, _payload: object) -> None:
        logger.debug("resume_event_received", signal_name="run_list_changed")
        self._rebuild_all_rows()

    def _on_run_touched(self, payload: object) -> None:
        if not isinstance(payload, _RUN_TOUCHED_EVENT_TYPES):
            return
        logger.debug("resume_event_received", signal_name="run_touched", run_id=payload.run_id)
        self._splice_row(payload.run_id)

    def _on_external_run_id_changed(self, payload: object) -> None:
        if not isinstance(payload, RunIdChangedEvent):
            return
        if payload.run_id == self._selected_run_id:
            return
        logger.debug("resume_event_received", signal_name="run_id_changed", run_id=payload.run_id)
        self._selected_run_id = payload.run_id

    def _on_task_file_changed(self, _payload: object) -> None:
        logger.debug("resume_event_received", signal_name="task_file_changed")
        self._rebuild_all_rows()

    def _rebuild_all_rows(self) -> None:
        runs = self._gateway.list_runs()
        results_by_run_id = {run.run_id: self._gateway.list_results(run.run_id) for run in runs}
        active_run_id = self._active_run_id()
        log_file_exists_by_run_id = {
            run.run_id: self._file_system_actions.run_log_exists(
                run_id=run.run_id, started_at=run.started_at
            )
            for run in runs
            if run.started_at
        }
        rows = select_run_rows(
            runs=runs,
            results_by_run_id=results_by_run_id,
            active_run_id=active_run_id,
            log_file_exists_by_run_id=log_file_exists_by_run_id,
        )
        self._apply_rows(rows)

    def _splice_row(self, run_id: RunId) -> None:
        run = self._gateway.get_run(run_id)
        results = self._gateway.list_results(run_id)
        log_file_exists = (
            self._file_system_actions.run_log_exists(run_id=run_id, started_at=run.started_at)
            if run.started_at
            else False
        )
        updated_row = select_run_rows(
            runs=(run,),
            results_by_run_id={run_id: results},
            active_run_id=self._active_run_id(),
            log_file_exists_by_run_id={run_id: log_file_exists},
        )[0]
        rows = tuple(updated_row if row.run_id == run_id else row for row in self._current_rows)
        if run_id not in {row.run_id for row in self._current_rows}:
            rows = (*rows, updated_row)
        self._apply_rows(rows)

    def _active_run_id(self) -> RunId | None:
        return self._gateway.active_run_id() if self._gateway.is_run_active() else None

    def _apply_rows(self, rows: tuple[RunRow, ...]) -> None:
        self._current_rows = rows
        self.table_model.set_rows(rows)
        self._clear_selection_if_filtered_out()
        self._push_resume_button_state()

    def _push_resume_button_state(self) -> None:
        if self._view is None:
            return
        view = cast("ResumeBenchmarkView", self._view)
        row = next((r for r in self._current_rows if r.run_id == self._selected_run_id), None)
        if row is None:
            view.set_resume_button_state(enabled=False, disabled_reason="Select a run to resume")
            return
        if row.is_executing:
            reason = "This run is currently running"
        elif not row.is_resumable:
            reason = "This run is fully completed — nothing to resume"
        else:
            reason = ""
        view.set_resume_button_state(enabled=row.is_resumable, disabled_reason=reason)

    def _clear_selection_if_filtered_out(self) -> None:
        if self._selected_run_id is None:
            return
        if self.table_model.find_view_row_for_run_id(self._selected_run_id) is None:
            self.on_row_selected(None)

    def rename_context_for(self, run_id: RunId) -> tuple[str | None, str]:
        """Return ``(current_custom_name, computed_default_name)`` for the Rename dialog.

        Args:
            run_id: The run about to be renamed.

        Returns:
            The run's current custom name (``None`` if it uses the default),
            and the computed default-name preview string (SPEC-077).
        """
        run = self._gateway.get_run(run_id)
        default_name = default_run_name(
            run_id=run.run_id, run_mode=run.run_mode, created_at=run.created_at
        )
        return run.run_name, default_name
