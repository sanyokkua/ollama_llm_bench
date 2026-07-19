"""``ResumeBenchmarkController`` -- EventBus subscriptions, selection, sort persistence
(STORY-056-AC-2). Depends only on ``ResumeGateway`` plus ``EventBus``, ``NativePickers``,
and ``FileSystemActions`` -- never a raw backend Store/Service Protocol (D-R-06).
"""

from functools import partial

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

    def _wire_menu_actions(self, menu: QMenu, row: RunRow) -> None:
        for action in menu.actions():
            name = action.objectName()
            if name == "action_clone":
                action.triggered.connect(partial(self._on_clone_triggered, row.run_id))
            elif name == "action_delete":
                action.triggered.connect(partial(self._on_delete_triggered, row))
            elif name == "action_export_analysis":
                action.triggered.connect(partial(self._on_export_analysis_triggered, row))
            elif name == "action_show_log":
                action.triggered.connect(partial(self._on_show_log_triggered, row))

    def _on_clone_triggered(self, source_run_id: RunId) -> None:
        logger.debug("resume_clone_triggered", source_run_id=source_run_id)
        new_run_id = clone_as_new_retry_run(gateway=self._gateway, source_run_id=source_run_id)
        self._rebuild_all_rows()
        self.on_row_selected(new_run_id)

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
        logger.debug("resume_event_received", event="run_list_changed")
        self._rebuild_all_rows()

    def _on_run_touched(self, payload: object) -> None:
        if not isinstance(payload, _RUN_TOUCHED_EVENT_TYPES):
            return
        logger.debug("resume_event_received", event="run_touched", run_id=payload.run_id)
        self._splice_row(payload.run_id)

    def _on_external_run_id_changed(self, payload: object) -> None:
        if not isinstance(payload, RunIdChangedEvent):
            return
        if payload.run_id == self._selected_run_id:
            return
        logger.debug("resume_event_received", event="run_id_changed", run_id=payload.run_id)
        self._selected_run_id = payload.run_id

    def _on_task_file_changed(self, _payload: object) -> None:
        logger.debug("resume_event_received", event="task_file_changed")
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
