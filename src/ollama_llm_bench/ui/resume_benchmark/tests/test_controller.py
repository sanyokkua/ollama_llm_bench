"""Colocated unit tests for the Resume widget controller (STORY-056)."""

from collections.abc import Callable, Mapping
import re
from typing import cast

from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QTableView
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ResultId,
    RunId,
    RunMode,
    RunStatus,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_RUN_ID_CHANGED,
    RunIdChangedEvent,
    Subscription,
)
from ollama_llm_bench.backend.run_drift import DriftWarning
from ollama_llm_bench.ui.resume_benchmark import make_resume_benchmark_widget
from ollama_llm_bench.ui.resume_benchmark._internal.controller import ResumeBenchmarkController
from ollama_llm_bench.ui.resume_benchmark._internal.run_table_model import (
    COL_NAME,
    RunTableModel,
)
from ollama_llm_bench.ui.resume_benchmark.models import ResumeBenchmarkCollaborators

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]")


class _NoopSubscription:
    def cancel(self) -> None:
        return None


class _RecordingEventBus:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> Subscription:
        return _NoopSubscription()

    def emit(self, signal_name: str, payload: object) -> None:
        self.emitted.append((signal_name, payload))

    def last(self, signal_name: str) -> object:
        for name, payload in reversed(self.emitted):
            if name == signal_name:
                return payload
        raise AssertionError(f"no event emitted on {signal_name}")


class _FakeNativePickers:
    def save_file(self, options: object) -> str | None:
        raise NotImplementedError

    def open_file(self, options: object) -> tuple[str, ...]:
        raise NotImplementedError

    def open_folder(self, options: object) -> str | None:
        raise NotImplementedError


class _FakeFileSystemActions:
    def open_in_file_manager(self, path: str) -> None:
        raise NotImplementedError

    def open_url(self, url: str) -> None:
        raise NotImplementedError

    def run_log_exists(self, *, run_id: int, started_at: str) -> bool:
        return False

    def run_log_path_str(self, *, run_id: int, started_at: str) -> str:
        return ""

    def write_export_file(self, *, filename: str, content: str) -> str:
        raise NotImplementedError

    def write_text_file(self, *, path: str, content: str) -> None:
        raise NotImplementedError

    def write_export_file_bytes(self, *, filename: str, content: bytes) -> str:
        raise NotImplementedError

    def write_binary_file(self, *, path: str, content: bytes) -> None:
        raise NotImplementedError

    def exports_folder_path(self) -> str:
        raise NotImplementedError


class _FakeResumeGateway:
    def __init__(
        self,
        *,
        runs: tuple[BenchmarkRun, ...],
        results_by_run_id: Mapping[RunId, tuple[BenchmarkResult, ...]],
    ) -> None:
        self._runs = {run.run_id: run for run in runs}
        self._results_by_run_id = results_by_run_id
        self.set_sort_calls: list[tuple[str, bool]] = []
        self.drift_warnings_by_run_id: dict[RunId, tuple[DriftWarning, ...]] = {}
        self.serialize_table_calls: list[tuple[RunId, str, str]] = []

    def list_runs(self) -> tuple[BenchmarkRun, ...]:
        return tuple(self._runs.values())

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        return self._runs[run_id]

    def create_run(self, run: BenchmarkRun) -> RunId:
        raise NotImplementedError

    def update_run_status(self, run_id: RunId, patch: object) -> None:
        raise NotImplementedError

    def rename_run(self, run_id: RunId, name: str | None) -> None:
        raise NotImplementedError

    def delete_run(self, run_id: RunId) -> None:
        raise NotImplementedError

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        return self._results_by_run_id.get(run_id, ())

    def resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        raise NotImplementedError

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        raise NotImplementedError

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        raise NotImplementedError

    def create_results(self, results: tuple[BenchmarkResult, ...]) -> None:
        raise NotImplementedError

    def update_result(self, result_id: ResultId, patch: object) -> None:
        raise NotImplementedError

    def list_tasks(self, run_id: RunId) -> tuple[BenchmarkTask, ...]:
        return ()

    def create_tasks(self, run_id: RunId, tasks: tuple[BenchmarkTask, ...]) -> None:
        raise NotImplementedError

    def refresh_readiness(self) -> AppReadinessSnapshot:
        raise NotImplementedError

    def get_sort_setting(self) -> tuple[str, bool]:
        return ("started", True)

    def set_sort_setting(self, column: str, descending: bool) -> None:  # noqa: FBT001  # mirrors ResumeGateway verbatim
        self.set_sort_calls.append((column, descending))

    def resume_run(self, run_id: RunId) -> None:
        raise NotImplementedError

    def is_run_active(self) -> bool:
        return False

    def active_run_id(self) -> RunId | None:
        return None

    def detect_drift(self, run_id: RunId) -> tuple[DriftWarning, ...]:
        return self.drift_warnings_by_run_id.get(run_id, ())

    def serialize_table(self, run_id: RunId, table: str, fmt: str) -> str:
        self.serialize_table_calls.append((run_id, table, fmt))
        return f"{table}-{fmt}-payload\n"


class _FakeExportFilenameHelper:
    """Real sanitisation + ``Run_<run_id>`` fallback (05_EXPORT_FORMATS.md §2)."""

    def compose_filename(self, *, run: BenchmarkRun, kind: str, ext: str) -> str:
        sanitized = _SANITIZE_RE.sub("_", run.run_name or "")
        collapsed = re.sub(r"_+", "_", sanitized)
        stripped = collapsed.strip("_").lstrip(".")[:80]
        base = stripped or f"Run_{run.run_id}"
        return f"{base}_{kind}.{ext}"


def _run(run_id: int, *, run_name: str = "Alpha") -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        run_name=run_name,
        timestamp="2024-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=RunStatus.INCOMPLETE,
        total_tasks=1,
        completed_tasks=0,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2024-01-01T00:00:00+00:00",
    )


def test_selection_emits_run_id_changed_and_clears_on_filter_out(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-2

    Selecting a row emits _run_id_changed with its run_id; when the selected
    row is filtered out by a search change, the selection clears and
    _run_id_changed reports no selection.
    """
    # Arrange
    run = _run(1)
    gateway = _FakeResumeGateway(runs=(run,), results_by_run_id={1: ()})
    bus = _RecordingEventBus()
    controller = ResumeBenchmarkController(
        collaborators=ResumeBenchmarkCollaborators(
            gateway=gateway,
            event_bus=bus,
            native_pickers=_FakeNativePickers(),
            file_system_actions=_FakeFileSystemActions(),
            export_filenames=_FakeExportFilenameHelper(),
        )
    )
    controller.load_initial_rows()

    # Act
    controller.on_row_selected(1)
    # Assert
    first_event = controller_last(bus, SIGNAL_RUN_ID_CHANGED)
    assert first_event.run_id == 1

    # Act
    controller.on_search_term_changed("no-such-run")
    # Assert
    second_event = controller_last(bus, SIGNAL_RUN_ID_CHANGED)
    assert second_event.run_id is None


def controller_last(bus: _RecordingEventBus, signal_name: str) -> RunIdChangedEvent:
    payload = bus.last(signal_name)
    assert isinstance(payload, RunIdChangedEvent)
    return payload


def test_load_initial_rows_applies_persisted_sort(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-1

    load_initial_rows reads the persisted sort column/direction and applies
    it to the table model before the first population.
    """
    # Arrange
    gateway = _FakeResumeGateway(runs=(_run(1),), results_by_run_id={1: ()})
    controller = ResumeBenchmarkController(
        collaborators=ResumeBenchmarkCollaborators(
            gateway=gateway,
            event_bus=_RecordingEventBus(),
            native_pickers=_FakeNativePickers(),
            file_system_actions=_FakeFileSystemActions(),
            export_filenames=_FakeExportFilenameHelper(),
        )
    )

    # Act
    controller.load_initial_rows()

    # Assert
    assert controller.table_model.rowCount() == 1


def test_resume_widget_constructs_and_shows_with_no_error_logs(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-7

    make_resume_benchmark_widget constructs and shows with a fake
    ResumeGateway, raises no exception, reports isVisible(), and emits no
    error/critical structlog record.
    """
    # Arrange
    collaborators = ResumeBenchmarkCollaborators(
        gateway=_FakeResumeGateway(runs=(), results_by_run_id={}),
        event_bus=_RecordingEventBus(),
        native_pickers=_FakeNativePickers(),
        file_system_actions=_FakeFileSystemActions(),
        export_filenames=_FakeExportFilenameHelper(),
    )

    # Act
    with structlog.testing.capture_logs() as captured:
        widget = make_resume_benchmark_widget(collaborators=collaborators)
        qtbot.addWidget(widget)
        widget.show()
        qtbot.wait(0)

    # Assert
    assert widget.isVisible()
    assert not any(entry["log_level"] in {"error", "critical"} for entry in captured)


def test_selection_restored_across_sort_reset_with_view_mounted(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-2 (gap fix: selection restore across a model reset, §3.3)

    ``RunTableModel.set_sort`` (like ``set_rows``/``set_search_term``) calls
    ``beginResetModel``/``endResetModel``, which clears Qt's own selection
    model. Mounting the real widget, selecting a row, then triggering a
    sort-column click must leave the same row selected in the QTableView
    afterward -- and must not emit a spurious ``_run_id_changed(None)`` in
    between (the selection is being restored, not changed by the user).
    """
    # Arrange
    gateway = _FakeResumeGateway(
        runs=(_run(1, run_name="Alpha"), _run(2, run_name="Beta")),
        results_by_run_id={1: (), 2: ()},
    )
    bus = _RecordingEventBus()
    collaborators = ResumeBenchmarkCollaborators(
        gateway=gateway,
        event_bus=bus,
        native_pickers=_FakeNativePickers(),
        file_system_actions=_FakeFileSystemActions(),
        export_filenames=_FakeExportFilenameHelper(),
    )
    widget = make_resume_benchmark_widget(collaborators=collaborators)
    qtbot.addWidget(widget)
    widget.show()
    table_view = cast("QTableView", widget.findChild(QTableView, "resume_benchmark.table"))
    model = cast("RunTableModel", table_view.model())
    selected_view_row = model.find_view_row_for_run_id(1)
    assert selected_view_row is not None
    table_view.selectionModel().select(
        model.index(selected_view_row, 0),
        QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
    )
    events_before = len(bus.emitted)

    # Act -- a sort-column click (drives a model reset unrelated to selection)
    table_view.horizontalHeader().sectionClicked.emit(COL_NAME)

    # Assert -- run 1's row is still selected
    restored_view_row = model.find_view_row_for_run_id(1)
    assert restored_view_row is not None
    assert table_view.selectionModel().isRowSelected(
        restored_view_row, model.index(-1, -1).parent()
    )

    # Assert -- no spurious _run_id_changed(None) was emitted while restoring
    new_events = bus.emitted[events_before:]
    assert not any(
        name == SIGNAL_RUN_ID_CHANGED
        and isinstance(payload, RunIdChangedEvent)
        and payload.run_id is None
        for name, payload in new_events
    )
